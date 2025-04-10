"""Tests for the workflow module."""

import logging
import shutil
import subprocess
from pathlib import Path

import pytest

from nipoppy.config.main import Config
from nipoppy.tabular.dicom_dir_map import DicomDirMap
from nipoppy.tabular.manifest import Manifest
from nipoppy.utils import FPATH_SAMPLE_CONFIG, FPATH_SAMPLE_MANIFEST
from nipoppy.workflows.base import BaseWorkflow

from .conftest import DPATH_TEST_DATA, create_empty_dataset, get_config, prepare_dataset


@pytest.fixture()
def workflow(tmp_path: Path):
    class DummyWorkflow(BaseWorkflow):
        def run_main(self):
            pass

    dpath_root = tmp_path / "my_dataset"
    workflow = DummyWorkflow(dpath_root=dpath_root, name="my_workflow")
    manifest = prepare_dataset(participants_and_sessions_manifest={})
    manifest.save_with_backup(workflow.layout.fpath_manifest)
    workflow.logger.setLevel(logging.DEBUG)  # capture all logs
    return workflow


def test_abstract_class():
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        BaseWorkflow(None, None)


def test_init(workflow: BaseWorkflow):
    assert isinstance(workflow.dpath_root, Path)


def test_generate_fpath_log(workflow: BaseWorkflow, datetime_fixture):  # noqa F811
    fpath_log = workflow.generate_fpath_log()
    assert isinstance(fpath_log, Path)
    assert (
        fpath_log
        == workflow.layout.dpath_logs / "my_workflow/my_workflow-20240404_1234.log"
    )


@pytest.mark.parametrize("fname_stem", ["123", "test", "my_workflow"])
def test_generate_fpath_log_custom(
    fname_stem,
    workflow: BaseWorkflow,
    datetime_fixture,  # noqa F811
):
    fpath_log = workflow.generate_fpath_log(fname_stem=fname_stem)
    assert isinstance(fpath_log, Path)
    assert (
        fpath_log
        == workflow.layout.dpath_logs / f"my_workflow/{fname_stem}-20240404_1234.log"
    )


@pytest.mark.parametrize("command", ["echo x", "echo y"])
@pytest.mark.parametrize("prefix_run", ["[RUN]", "<run>"])
def test_log_command(
    workflow: BaseWorkflow, command, prefix_run, caplog: pytest.LogCaptureFixture
):
    workflow.log_prefix_run = prefix_run
    workflow.log_command(command)
    assert caplog.records
    record = caplog.records[-1]
    assert record.levelno == logging.INFO
    assert record.message.startswith(prefix_run)
    assert command in record.message


def test_log_command_no_markup(
    workflow: BaseWorkflow, caplog: pytest.LogCaptureFixture
):
    # message with closing tag
    message = "[/]"

    # this should not raise a rich markup error
    workflow.run_command(["echo", message])
    assert message in caplog.text


def test_run_command(workflow: BaseWorkflow, tmp_path: Path):
    fpath = tmp_path / "test.txt"
    process = workflow.run_command(["touch", fpath])
    assert process.returncode == 0
    assert fpath.exists()


def test_run_command_single_string(workflow: BaseWorkflow, tmp_path: Path):
    fpath = tmp_path / "test.txt"
    process = workflow.run_command(f"touch {fpath}", shell=True)
    assert process.returncode == 0
    assert fpath.exists()


def test_run_command_dry_run(workflow: BaseWorkflow, tmp_path: Path):
    workflow.dry_run = True
    fpath = tmp_path / "test.txt"
    command = workflow.run_command(["touch", fpath])
    assert command == f"touch {fpath}"
    assert not fpath.exists()


def test_run_command_check(workflow: BaseWorkflow):
    with pytest.raises(subprocess.CalledProcessError):
        workflow.run_command(["which", "probably_fake_command"], check=True)


def test_run_command_no_markup(
    workflow: BaseWorkflow, caplog: pytest.LogCaptureFixture, tmp_path: Path
):
    # text with closing tag
    text = "[/]"

    # this should not raise a rich markup error
    fpath_txt = tmp_path / "test.txt"
    fpath_txt.write_text(text)
    workflow.run_command(["cat", fpath_txt])
    assert text in caplog.text


def test_run_command_quiet(workflow: BaseWorkflow, caplog: pytest.LogCaptureFixture):
    message = "This should be printed"
    workflow.run_command(["echo", message], quiet=True)
    assert workflow.log_prefix_run not in caplog.text
    assert message in caplog.text


def test_run_setup(workflow: BaseWorkflow, caplog: pytest.LogCaptureFixture):
    create_empty_dataset(workflow.dpath_root)
    workflow.run_setup()
    assert "BEGIN" in caplog.text


def test_run(workflow: BaseWorkflow):
    create_empty_dataset(workflow.dpath_root)
    assert workflow.run() is None


def test_run_cleanup(workflow: BaseWorkflow, caplog: pytest.LogCaptureFixture):
    workflow.run_cleanup()
    assert "END" in caplog.text


@pytest.mark.parametrize(
    "fpath_config",
    [
        FPATH_SAMPLE_CONFIG,
        DPATH_TEST_DATA / "config1.json",
        DPATH_TEST_DATA / "config2.json",
        DPATH_TEST_DATA / "config3.json",
    ],
)
def test_config(workflow: BaseWorkflow, fpath_config):
    workflow.layout.fpath_config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fpath_config, workflow.layout.fpath_config)
    assert isinstance(workflow.config, Config)


def test_config_not_found(workflow: BaseWorkflow):
    with pytest.raises(FileNotFoundError):
        workflow.config


def test_config_replacement(workflow: BaseWorkflow):
    config = get_config(dataset_name="[[NIPOPPY_DPATH_ROOT]]")
    config.save(workflow.layout.fpath_config)
    assert str(workflow.config.DATASET_NAME) == str(workflow.dpath_root)


def test_manifest(workflow: BaseWorkflow):
    workflow.layout.fpath_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FPATH_SAMPLE_MANIFEST, workflow.layout.fpath_manifest)
    config = get_config(
        visit_ids=["BL", "M12"],
    )
    workflow.layout.fpath_config.parent.mkdir(parents=True, exist_ok=True)
    config.save(workflow.layout.fpath_config)
    assert isinstance(workflow.manifest, Manifest)


def test_manifest_not_found(workflow: BaseWorkflow):
    with pytest.raises(FileNotFoundError):
        workflow.manifest


def test_dicom_dir_map(workflow: BaseWorkflow):
    workflow.config = get_config()
    assert isinstance(workflow.dicom_dir_map, DicomDirMap)


def test_dicom_dir_map_custom(workflow: BaseWorkflow):
    workflow.config = get_config()
    workflow.config.DICOM_DIR_MAP_FILE = DPATH_TEST_DATA / "dicom_dir_map1.tsv"
    assert isinstance(workflow.dicom_dir_map, DicomDirMap)


def test_dicom_dir_map_not_found(workflow: BaseWorkflow):
    workflow.config = get_config()
    workflow.config.DICOM_DIR_MAP_FILE = "fake_path"
    with pytest.raises(FileNotFoundError, match="DICOM directory map file not found"):
        workflow.dicom_dir_map


def test_processing_status_empty_if_not_found(workflow: BaseWorkflow):
    assert not workflow.layout.fpath_processing_status.exists()
    assert len(workflow.processing_status_table) == 0
