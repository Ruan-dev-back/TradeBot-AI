"""Run the offline suite, preserve its exit code and annotate actual failures."""

import re
import subprocess
import sys


def main():
    command = ['docker', 'compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.audit.yml',
               'run', '--rm', 'freqtrade', 'test']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout, end='', flush=True)
    if result.returncode:
        failures = re.findall(r'(?:ERROR|FAIL): .*?(?=\n={10,}|\n-{10,}\nRan |\Z)',
                              result.stdout, flags=re.S)
        for block in failures or [result.stdout[-5000:]]:
            escaped = block[-5000:].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
            print('::error title=Offline suite failure::' + escaped, flush=True)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
