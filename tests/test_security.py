import importlib.util
import subprocess
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pilot'))
from screen import archive_tree, sh
from blind import junit_results


def test_git_archive_does_not_interpret_shell_characters(tmp_path):
    repo=tmp_path/'repo ; echo unsafe'
    repo.mkdir()
    subprocess.run(['git','init','-q',str(repo)],check=True)
    (repo/'sample.txt').write_text('safe')
    subprocess.run(['git','-C',str(repo),'add','.'],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','initial'],check=True)
    dest=tmp_path/'output ; echo unsafe'
    dest.mkdir()
    archive_tree(repo,'HEAD',dest)
    assert (dest/'sample.txt').read_text()=='safe'
    with pytest.raises(subprocess.CalledProcessError):
        archive_tree(repo,'HEAD; touch SHOULD_NOT_EXIST',dest)
    assert not (Path.cwd()/'SHOULD_NOT_EXIST').exists()


def test_command_helper_rejects_shell_strings():
    with pytest.raises(TypeError): sh('echo unsafe')


def test_xml_reports_reject_entity_expansion(tmp_path):
    report=tmp_path/'report.xml'
    report.write_text('<!DOCTYPE x [<!ENTITY attack "expanded">]><testsuite><testcase name="&attack;"/></testsuite>')
    from defusedxml.common import DefusedXmlException
    with pytest.raises(DefusedXmlException):junit_results(report)
