"""Render reviewable units; never installs/enables services or changes accounts."""
import argparse
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
FILES=('tradebot-okx-paper.service','tradebot-paper-observer.service',
       'tradebot-paper-health.service','tradebot-paper-health.timer')


def render(target, checkout, user, group, external_docker=False, docker_binary=None, python_binary=None):
    if not all(re.fullmatch(r'[a-z_][a-z0-9_-]*',name) for name in (user,group)):
        raise ValueError('Use real Linux account/group names')
    checkout=Path(checkout)
    if (not checkout.is_absolute() or re.search(r'[\s%\\\r\n]',str(checkout))):
        raise ValueError('Use an absolute checkout without whitespace/systemd specifiers')
    target=Path(target)
    if target.exists():raise ValueError('Render to a new directory; review before installation')
    target.mkdir(parents=True)
    docker_binary=str(docker_binary or shutil.which('docker') or '/usr/bin/docker')
    python_binary=str(python_binary or sys.executable)
    for binary in (docker_binary,python_binary):
        if not Path(binary).is_absolute() or re.search(r'[\s%\\\r\n]',binary):
            raise ValueError('Use absolute executable paths without systemd specifiers')
    for name in FILES:
        text=(ROOT/'infra'/name).read_text().replace('/opt/tradebot-ai',str(checkout))
        text=text.replace('User=tradebot','User='+user).replace('Group=tradebot','Group='+group)
        if external_docker:
            text=text.replace('Requires=docker.service tradebot-okx-paper.service','Requires=tradebot-okx-paper.service')
            text=text.replace('Requires=docker.service\n','').replace('After=docker.service ','After=')
            text=text.replace('After=docker.service\n','').replace('SupplementaryGroups=docker\n','')
            if name=='tradebot-okx-paper.service':
                text=text.replace('ExecStartPre=/usr/bin/python3','ExecStartPre=/usr/bin/docker info --format {{.OSType}}\nExecStartPre=/usr/bin/python3',1)
        text=text.replace('/usr/bin/docker',docker_binary).replace('/usr/bin/python3',python_binary)
        (target/name).write_text(text)
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--checkout',type=Path,required=True)
    parser.add_argument('--user',required=True);parser.add_argument('--group',required=True)
    parser.add_argument('--external-docker',action='store_true')
    parser.add_argument('--docker-binary',type=Path);parser.add_argument('--python-binary',type=Path)
    args=parser.parse_args()
    try:print(render(args.output,args.checkout,args.user,args.group,args.external_docker,args.docker_binary,args.python_binary))
    except (OSError,ValueError) as error:parser.error(str(error))


if __name__=='__main__':main()
