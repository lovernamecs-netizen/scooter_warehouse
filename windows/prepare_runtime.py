"""Prepare a PC-local Python environment, then launch the existing-data server."""
from contextlib import contextmanager
from pathlib import Path
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ('requirements.txt', 'requirements-google.txt', 'requirements-insurance.txt')


def usable(executable):
    if not executable.is_file():
        return False
    try:
        result = subprocess.run(
            [str(executable), '-I', '-c',
             "import sys,struct; sys.exit(0 if sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def dependencies_ready(executable, root):
    # pip's bundled parser also handles extras and platform/version markers.
    check = """
import sys
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
from pip._vendor.packaging.requirements import Requirement
for filename in sys.argv[1:]:
    for line in Path(filename).read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        req = Requirement(line)
        if req.marker and not req.marker.evaluate():
            continue
        try:
            installed = version(req.name)
        except PackageNotFoundError:
            sys.exit(1)
        if installed not in req.specifier:
            sys.exit(1)
import fastapi, uvicorn, sqlalchemy, cryptography, multipart, openpyxl
import PIL, pillow_heif, httpx, google.auth, requests, pymupdf, xlrd, keyring, solapi
"""
    result = subprocess.run(
        [str(executable), '-I', '-c', check, *[str(root / name) for name in REQUIREMENTS]],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
    )
    return result.returncode == 0


@contextmanager
def setup_lock(root):
    import msvcrt
    with (root / '.runtime-setup.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        deadline = time.monotonic() + 1800
        while True:
            try:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('다른 설치 작업이 진행 중입니다. 완료 후 다시 실행하세요.')
                time.sleep(1)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def prepare(root):
    existing = root / '.venv' / 'Scripts' / 'python.exe'
    if usable(existing) and dependencies_ready(existing, root):
        return existing
    # Preserve the copied environment and build/repair a separate local runtime.
    environment = root / '.venv-local'
    if environment.is_symlink() or environment.is_junction():
        raise RuntimeError('실행 환경 폴더가 연결 경로입니다. .venv-local 경로를 확인하세요.')
    executable = environment / 'Scripts' / 'python.exe'
    if not usable(executable):
        print('이 PC에 맞는 Python 실행 환경을 구성합니다.', flush=True)
        base = getattr(sys, '_base_executable', sys.executable)
        command = [base, '-I', '-m', 'venv', str(environment)]
        if (environment / 'pyvenv.cfg').exists():
            command.append('--upgrade')
        subprocess.run(command, check=True)
    if not dependencies_ready(executable, root):
        print('필요한 패키지를 설치합니다. 첫 실행에는 시간이 걸립니다.', flush=True)
        command = [str(executable), '-I', '-m', 'pip', 'install', '--disable-pip-version-check']
        for filename in REQUIREMENTS:
            command.extend(['-r', str(root / filename)])
        subprocess.run(command, check=True)
        if not dependencies_ready(executable, root):
            raise RuntimeError('패키지 설치 검증에 실패했습니다. 위 오류를 확인하세요.')
    return executable


def main():
    os.chdir(ROOT)
    with setup_lock(ROOT):
        executable = prepare(ROOT)
    if '--setup-only' in sys.argv:
        print('실행 환경 준비 완료', flush=True)
        return 0
    return subprocess.call([str(executable), str(ROOT / 'windows' / 'start_local.py')])


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print('시작 준비 실패. 인터넷 연결과 설치 오류를 확인한 뒤 다시 실행하세요.', flush=True)
        print(str(error), flush=True)
        sys.exit(1)
