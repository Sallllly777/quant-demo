"""Verify the immutable submitted simulation bundle using the CURRENT verifier."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parents[1]
EXPECTED='b44265d47db63e54bda2100e8bca130cf9112a5c5fe834bed253dfb80105f583'

def main():
    bundle=ROOT/'docs/evidence/20261008-ag2612/evidence.zip'
    if hashlib.sha256(bundle.read_bytes()).hexdigest()!=EXPECTED: raise ValueError('Evidence ZIP hash changed')
    cache=ROOT/'.cache'; cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temp:
        folder=Path(temp).resolve()
        with zipfile.ZipFile(bundle) as z:
            for member in z.infolist():
                if not (folder/member.filename).resolve().is_relative_to(folder): raise ValueError('Unsafe archive path')
            for line in z.read('SHA256SUMS.txt').decode('utf-8').splitlines():
                if not line.strip(): continue
                expected,name=line.split('  ',1)
                if hashlib.sha256(z.read(name)).hexdigest()!=expected: raise ValueError('Member checksum mismatch: '+name)
            z.extractall(folder)
        base=folder/'data/simnow_checks'
        command=[sys.executable,'-B',str(ROOT/'scripts/simnow/verify_acceptance.py'),
            '--trade',str(base/'20261008-235242-acceptance-67c370'),
            '--reference',str(base/'20261008-235327-acceptance-d71dc1'),
            '--capture',str(base/'20261008-235417-e7e9f4'),
            '--capture',str(base/'20261008-235715-b50c3a'),
            '--output',str(folder/'current_verification')]
        subprocess.run(command,check=True)
    print('Archive hash, every member hash and current acceptance checks passed.')

if __name__=='__main__': main()
