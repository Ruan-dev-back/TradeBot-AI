"""Linux/WSL2 host operations. Fixed dry-run profiles, no system installation/deploy."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

from audit_guard import verify_baseline, require_locked_holdout
from paper_health import readonly
from paper_monitor import collect, manifest, observer_health, summary
from paper_profiles import profile_for
from state_bundle import create_backup, inspect_state, paths, restore_bundle, verify_bundle

ROOT = Path(__file__).resolve().parents[1]


def compose(root, exchange, cloud=False):
    profile = profile_for(exchange)
    command = ['docker','compose','-f',str(root/profile.compose_file)]
    if cloud:
        command += ['-f',str(root/profile.compose_file.replace('.yml','.cloud.yml'))]
    return command


def execute(command, root=ROOT, timeout=180):
    result = subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        raise ValueError('Command failed: '+command[0]+' '+command[1]+' (exit '+str(result.returncode)+')')
    return result.stdout


def image_for(root, exchange):
    # Compose is parsed by Docker, never by shell interpolation or a mutable tag.
    config = json.loads(execute(compose(root,exchange)+['config','--format','json'],root))
    image = config['services'][profile_for(exchange).service]['image']
    if not image.startswith('freqtradeorg/freqtrade:stable@sha256:') or len(image.rsplit(':',1)[-1])!=64:
        raise ValueError('Pinned official image is required')
    return image


def static_checks(root, exchange):
    verify_baseline(); require_locked_holdout(); manifest(exchange)
    config = json.loads((root/'user_data'/profile_for(exchange).config_file).read_text())
    if (config.get('dry_run') is not True or config.get('trading_mode')!='spot'
            or config.get('margin_mode')!='' or config.get('force_entry_enable') is not False
            or any(config['exchange'].get(k) for k in ('key','secret','password','uid'))):
        raise ValueError('Public spot dry-run configuration required')
    if any(name.startswith('FREQTRADE__') for name in os.environ):
        raise ValueError('Freqtrade environment overrides refused')
    if str(root.resolve()).startswith('/mnt/'):
        raise ValueError('Keep code/state in WSL Linux ext4, not /mnt/c, network or synced folders')


def preflight(root=ROOT, exchange='okx', cloud=False, public=True):
    static_checks(root,exchange)
    if execute(['docker','info','--format','{{.OSType}}'],root).strip()!='linux':
        raise ValueError('Linux Docker engine required')
    if execute(['docker','info','--format','{{.Architecture}}'],root).strip() not in ('x86_64','amd64'):
        raise ValueError('Only tested x86_64 host/image is supported; validate other architectures separately')
    version=execute(['docker','compose','version','--short'],root).strip().lstrip('v')
    import re
    match=re.match(r'(\d+)\.(\d+)\.',version)
    if not match or tuple(map(int,match.groups()))<(2,40):
        raise ValueError('Docker Compose >=2.40 required for the tested workflow')
    execute(compose(root,exchange,cloud)+['config','--quiet'],root)
    image = image_for(root,exchange)
    details=json.loads(execute(['docker','run','--rm','--network','none','--entrypoint','python',image,'-c',
        'import os,json; print(json.dumps({"uid":os.getuid(),"gid":os.getgid()}))'],root))
    if os.getuid()!=details['uid']:
        raise ValueError('Host/service UID must match pinned ftuser UID '+str(details['uid'])+'; do not use chmod777 or override container user')
    for path in paths(root,exchange).values():
        if path.exists() and (not os.access(path,os.R_OK|os.W_OK) or path.stat().st_uid!=os.getuid()):
            raise ValueError('Runtime database ownership/access mismatch')
    if public:
        p=profile_for(exchange)
        script='check_okx.py' if exchange=='okx' else 'check_market.py'
        execute(compose(root,exchange,cloud)+['run','--rm','--entrypoint','python',p.service,
                 '/freqtrade/scripts/'+script],root,timeout=300)
    return {'status':'preflight_passed','exchange':exchange,'uid':details['uid'],
            'gid':details['gid'],'image':image,'public_api_checked':public,
            'region_account_eligibility_verified':False}


def recovery(root=ROOT, exchange='okx'):
    static_checks(root,exchange)
    result=inspect_state(paths(root,exchange),exchange,ROOT)
    return {**result,'status':'state_verified_live_health_pending',
            'now_utc':datetime.now(timezone.utc).isoformat()}


def observer_locked(root, exchange):
    folder=root/'user_data/observation'/exchange
    folder.mkdir(parents=True,exist_ok=True)
    with open(folder/'observer.lock','a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
    return False


def process_identity(pid):
    # Linux /proc start-time prevents signalling a recycled PID.
    text=Path('/proc/'+str(pid)+'/stat').read_text()
    return text[text.rfind(')')+2:].split()[19]


def stop_observer(root, exchange):
    record=root/'user_data/host-ops'/exchange/'observer.json'
    if not observer_locked(root,exchange):return {'observer':'not_running'}
    if not record.is_file():
        raise ValueError('Unmanaged observer: use Ctrl+C or systemctl stop; never kill an unknown PID')
    owner=json.loads(record.read_text());pid=owner['pid']
    try:
        command=Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(b'\0')
        expected=str(root/'scripts/paper_monitor.py').encode()
        if (process_identity(pid)!=owner['start_ticks'] or expected not in command
                or exchange.encode() not in command):
            raise ValueError('Observer PID identity mismatch; no signal sent')
        os.kill(pid,signal.SIGINT)
        deadline=time.monotonic()+15
        while observer_locked(root,exchange) and time.monotonic()<deadline:time.sleep(.1)
        if observer_locked(root,exchange):raise ValueError('Observer did not release its lock; no forced kill')
        return {'observer':'stopped_preserving_window'}
    except FileNotFoundError:
        if observer_locked(root,exchange):raise ValueError('Observer owner is unknown')
        return {'observer':'already_stopped'}


def start(root=ROOT, exchange='okx', cloud=False):
    recovery(root,exchange)  # Missing journal is never permission to create a new T0.
    preflight(root,exchange,cloud)
    p=profile_for(exchange)
    execute(compose(root,exchange,cloud)+['up','-d','--wait','--wait-timeout','90',p.service],root,timeout=180)
    if observer_locked(root,exchange):
        return {'status':'bot_ready_observer_already_active','exchange':exchange}
    folder=root/'user_data/host-ops'/exchange;folder.mkdir(parents=True,exist_ok=True)
    log=root/'user_data/logs'/('observer-'+exchange+'.log');log.parent.mkdir(parents=True,exist_ok=True)
    with open(log,'a') as output:
        child=subprocess.Popen([sys.executable,str(root/'scripts/paper_monitor.py'),'watch','--exchange',exchange],
             cwd=root,stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True)
    record={'pid':child.pid,'start_ticks':process_identity(child.pid),'started_utc':datetime.now(timezone.utc).isoformat()}
    (folder/'observer.json').write_text(json.dumps(record)+'\n')
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        if child.poll() is not None:raise ValueError('Observer exited; review local log, no replacement window')
        try:
            observer_health(root/'user_data/observation'/exchange/'journal.sqlite',datetime.now(timezone.utc))
            return {'status':'bot_and_observer_ready','exchange':exchange,'observer_pid':child.pid}
        except (ValueError,OSError,sqlite3.Error):time.sleep(.2)
    raise ValueError('Observer readiness timeout; process retained for diagnosis')


def dispatch(args, parser):
    # Serializes operators; the bot and observer retain their independent writer locks.
    folder=ROOT/'user_data/host-ops'/args.exchange
    folder.mkdir(parents=True,exist_ok=True)
    with open(folder/'operations.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return perform(args,parser)


def perform(args,parser):
    if args.command=='run-observer':
        recovery(exchange=args.exchange)
        os.execv(sys.executable,[sys.executable,str(ROOT/'scripts/paper_monitor.py'),'watch','--exchange',args.exchange])
    if args.command=='setup':
        static_checks(ROOT,args.exchange)
        execute(['docker','pull',image_for(ROOT,args.exchange)],ROOT,timeout=300)
        result=preflight(exchange=args.exchange,cloud=args.cloud,public=False)
    elif args.command=='preflight':result=preflight(exchange=args.exchange,cloud=args.cloud)
    elif args.command=='start':result=start(exchange=args.exchange,cloud=args.cloud)
    elif args.command=='stop':
        result=stop_observer(ROOT,args.exchange)
        execute(compose(ROOT,args.exchange,args.cloud)+['stop',profile_for(args.exchange).service])
    elif args.command=='status':
        result=collect(exchange=args.exchange);print(summary(result))
        return 0 if result['healthy'] and not result['entries_blocked'] else 2
    elif args.command=='export':
        return subprocess.call([sys.executable,str(ROOT/'scripts/paper_monitor.py'),'export','--exchange',args.exchange])
    elif args.command=='backup':result={'backup':str(create_backup(ROOT,args.exchange))}
    elif args.command=='verify-backup':
        if not args.bundle:parser.error('--bundle required')
        result=verify_bundle(args.bundle,args.exchange)
    elif args.command=='restore':
        if not args.bundle or not args.target:parser.error('--bundle and --target required')
        result=restore_bundle(args.bundle,args.target,args.exchange)
    else:result=recovery(exchange=args.exchange)
    print(json.dumps(result,indent=2));return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['setup','preflight','start','stop','status','export','backup',
                                          'verify-backup','restore','verify-recovery','run-observer'])
    parser.add_argument('--exchange',choices=['okx','kraken'],default='okx')
    parser.add_argument('--cloud',action='store_true')
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--target',type=Path)
    args=parser.parse_args()
    try:
        if sys.version_info<(3,10):raise ValueError('Host Python >=3.10 required')
        # A foreground observer must not hold the operations lock through exec.
        return perform(args,parser) if args.command=='run-observer' else dispatch(args,parser)
    except (ValueError,OSError,KeyError,TypeError,sqlite3.Error,subprocess.SubprocessError) as error:
        print(json.dumps({'status':'refused','error_type':type(error).__name__,
                         'reason':str(error) if isinstance(error,ValueError) else 'check host prerequisites/state; no private values printed'}),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
