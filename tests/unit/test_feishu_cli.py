"""采集 CLI 默认行为；使用模拟 Store，不连接数据库或外部服务。"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import feishu_cli
from tests.unit.test_feishu_config_and_events import config_path


@pytest.fixture
def cli_store(monkeypatch):
    store=MagicMock()
    store.counts.return_value={"pending_messages":0,"failed_messages":0,"pending_receipts":0,"failed_receipts":0}
    monkeypatch.setattr(feishu_cli,'Store',lambda url:store)
    monkeypatch.setattr(feishu_cli,'database_url',lambda snapshot:'unused_mock_url')
    monkeypatch.setattr(feishu_cli,'load_dotenv',lambda *args,**kwargs:None)
    monkeypatch.setattr(feishu_cli,'configure_logs',lambda *args,**kwargs:None)
    return store


def test_validate_never_constructs_store(config_path,monkeypatch,capsys):
    def forbidden(*args,**kwargs): raise AssertionError('校验不得访问状态库')
    monkeypatch.setattr(feishu_cli,'Store',forbidden)
    monkeypatch.setattr(feishu_cli,'load_dotenv',lambda *args,**kwargs:None)
    assert feishu_cli.main(['--config',str(config_path),'validate']) == 0
    assert json.loads(capsys.readouterr().out)['valid']


def test_cli_resolves_custom_config_from_local_dotenv(config_path,monkeypatch,capsys):
    monkeypatch.chdir(config_path.parent)
    monkeypatch.delenv('FEISHU_CONFIG_PATH',raising=False)
    (config_path.parent / '.env').write_text(f'FEISHU_CONFIG_PATH={config_path.name}\n')
    def forbidden(*args, **kwargs):
        raise AssertionError('校验不得访问状态库')
    monkeypatch.setattr(feishu_cli,'Store',forbidden)
    assert feishu_cli.main(['validate']) == 0
    assert json.loads(capsys.readouterr().out)['valid']


def test_sources_queries_metadata_and_closes_store(config_path,cli_store,capsys):
    cli_store.sources.return_value=[{'chat_id':'oc_example','sender_open_id':'ou_example'}]
    assert feishu_cli.main(['--config',str(config_path),'sources','--app','personal','--kind','group','--offset','10']) == 0
    cli_store.sources.assert_called_once_with('personal','group',100,10)
    cli_store.close.assert_called_once()
    assert 'sender_open_id' in capsys.readouterr().out


def test_status_has_collection_only(config_path,cli_store,capsys):
    cli_store.streams.return_value=[SimpleNamespace(id='instance',pipeline='inspiration',input_path='/example/messages.md')]
    assert feishu_cli.main(['--config',str(config_path),'status']) == 0
    result=json.loads(capsys.readouterr().out)
    assert result['pending_messages'] == 0 and result['streams'][0]['pipeline'] == 'inspiration'
    assert 'runs' not in result


@pytest.mark.parametrize('command',['worker','process','retry'])
def test_ai_commands_are_removed(command,config_path,cli_store,capsys):
    with pytest.raises(SystemExit) as result:
        feishu_cli.main(['--config',str(config_path),command])
    assert result.value.code == 2
    cli_store.streams.assert_not_called()
    capsys.readouterr()


def test_compatibility_worker_reads_new_config_from_dotenv(tmp_path,monkeypatch):
    from app.workers.feishu_inspiration import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('FEISHU_CONFIG_PATH',raising=False)
    (tmp_path/'.env').write_text('FEISHU_CONFIG_PATH=config/from-env.toml\n')
    delegate=MagicMock(return_value=0)
    monkeypatch.setattr(feishu_cli,'main',delegate)
    with pytest.raises(SystemExit) as result: main()
    assert result.value.code == 0
    delegate.assert_called_once_with(['--config','config/from-env.toml','collect'])


def test_state_errors_never_print_sql_or_private_body(config_path,cli_store,capsys):
    from sqlalchemy.exc import OperationalError
    cli_store.streams.side_effect=OperationalError('private SQL',{'secret':'private'},RuntimeError('private password'))
    assert feishu_cli.main(['--config',str(config_path),'status']) == 1
    output=capsys.readouterr().out
    assert json.loads(output)['error_code'] == 'collection_state_error'
    assert 'private' not in output and 'password' not in output
