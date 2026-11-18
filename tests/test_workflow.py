from pathlib import Path

import yaml

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "build-windows.yml"


def load():
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = wf.get("on") or wf.get(True)  # PyYAML reads the bare key `on` as the boolean True
    steps = wf["jobs"]["build"]["steps"]
    runs = "\n".join(str(s.get("run", "")) for s in steps)
    uses = [str(s.get("uses", "")) for s in steps]
    return wf, triggers, steps, runs, uses


def test_runs_on_windows_with_python_312():
    wf, _, steps, _, uses = load()
    assert wf["jobs"]["build"]["runs-on"] == "windows-latest"
    setup = [s for s in steps if str(s.get("uses", "")).startswith("actions/setup-python")]
    assert setup and str(setup[0]["with"]["python-version"]) == "3.12"


def test_triggers_manual_and_version_tags():
    _, triggers, _, _, _ = load()
    assert "workflow_dispatch" in triggers
    assert "v*" in triggers["push"]["tags"]


def test_tests_build_and_smoke_test_steps_exist_in_order():
    _, _, _, runs, _ = load()
    assert runs.index("pytest") < runs.index("pyinstaller") < runs.index("--selftest")
    assert "subocr.exe" in runs and "make_smoke_video.py" in runs


def test_smoke_test_waits_for_the_windowed_exe_and_checks_events():
    _, _, _, runs, _ = load()
    assert "Start-Process" in runs and "-Wait" in runs  # a windowed exe returns immediately otherwise
    assert "selftest.json" in runs and "events" in runs


def test_uploads_artifact_and_attaches_to_release_on_tags():
    wf, _, steps, _, uses = load()
    assert any(u.startswith("actions/upload-artifact") for u in uses)
    release = [s for s in steps if str(s.get("uses", "")).startswith("softprops/action-gh-release")]
    assert release and "refs/tags/" in str(release[0]["if"])
    assert wf["permissions"]["contents"] == "write"
