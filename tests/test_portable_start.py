"""Portable startup regression tests. Never installs Python or downloads packages."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_runtime', ROOT / 'windows/prepare_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows startup')


def test_existing_runtime_is_reused_without_install(tmp_path):
    with patch.object(runtime, 'usable', return_value=True), patch.object(runtime, 'dependencies_ready', return_value=True), patch.object(runtime.subprocess, 'run') as run:
        assert runtime.prepare(tmp_path) == tmp_path / '.venv/Scripts/python.exe'
        run.assert_not_called()


def test_copied_broken_environment_preserved_and_local_created(tmp_path):
    old = tmp_path / '.venv'
    old.mkdir()
    config = old / 'pyvenv.cfg'
    config.write_text('home = C:\\missing-source-PC\\Python312', encoding='utf-8')
    db = tmp_path / 'warehouse.db'
    db.write_bytes(b'synthetic database marker')
    photos = tmp_path / 'Data'
    photos.mkdir()
    photo = photos / 'synthetic.jpg'
    photo.write_bytes(b'synthetic photo marker')
    with patch.object(runtime, 'usable', return_value=False), patch.object(runtime, 'dependencies_ready', side_effect=[False, True]), patch.object(runtime.subprocess, 'run') as run:
        result = runtime.prepare(tmp_path)
    assert result == tmp_path / '.venv-local/Scripts/python.exe'
    assert run.call_args_list[0].args[0][-1] == str(tmp_path / '.venv-local')
    assert 'pip' in run.call_args_list[1].args[0]
    assert config.read_text() == 'home = C:\\missing-source-PC\\Python312'
    assert db.read_bytes() == b'synthetic database marker'
    assert photo.read_bytes() == b'synthetic photo marker'


def test_install_failure_stops_and_can_retry(tmp_path):
    with patch.object(runtime, 'usable', return_value=True), patch.object(runtime, 'dependencies_ready', return_value=False), patch.object(runtime.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'pip')):
        with pytest.raises(subprocess.CalledProcessError):
            runtime.prepare(tmp_path)
    with patch.object(runtime, 'usable', return_value=True), patch.object(runtime, 'dependencies_ready', side_effect=[False, True]), patch.object(runtime.subprocess, 'run') as run:
        assert runtime.prepare(tmp_path) == tmp_path / '.venv-local/Scripts/python.exe'
        run.assert_not_called()


@pytest.mark.parametrize('environment', ['valid', 'missing', 'copied'])
def test_batch_entry_with_spaces_and_korean_path(tmp_path, environment):
    root = tmp_path / '다른 PC 서버'
    windows = root / 'windows'
    windows.mkdir(parents=True)
    base = getattr(sys, '_base_executable', sys.executable)
    if environment != 'missing':
        subprocess.run([base, '-m', 'venv', '--without-pip', str(root / '.venv')], check=True, capture_output=True)
    if environment == 'copied':
        (root / '.venv/pyvenv.cfg').write_text('home = C:\\missing-source-PC\\Python312\n', encoding='utf-8')
    shutil.copy2(ROOT / 'windows/START_LOCAL_SERVER.cmd', windows)
    # The entry-point test deliberately substitutes preparation to avoid installations.
    (windows / 'prepare_runtime.py').write_text("from pathlib import Path\nPath('entry-reached').write_text('ok')\n", encoding='utf-8')
    result = subprocess.run(['cmd.exe', '/d', '/c', str(windows / 'START_LOCAL_SERVER.cmd')], cwd=tmp_path, stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / 'entry-reached').read_text() == 'ok'
    assert not (root / 'warehouse.db').exists()


def test_broken_python_executable_is_detected(tmp_path):
    fake = tmp_path / 'python.exe'
    fake.write_bytes(b'not a Windows executable')
    assert not runtime.usable(fake)


def test_setup_lock_releases_after_failure(tmp_path):
    with pytest.raises(RuntimeError):
        with runtime.setup_lock(tmp_path):
            raise RuntimeError('synthetic setup failure')
    with runtime.setup_lock(tmp_path):
        pass
