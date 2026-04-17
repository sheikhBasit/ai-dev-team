"""Tests for detect_frontend_target() in project_detector.py."""


from ai_team.agents.project_detector import detect_frontend_target


def test_tauri_conf_json_returns_desktop(tmp_path):
    (tmp_path / "tauri.conf.json").write_text("{}")
    assert detect_frontend_target(str(tmp_path)) == "desktop"


def test_build_gradle_kts_returns_mobile(tmp_path):
    (tmp_path / "build.gradle.kts").write_text("// android build")
    assert detect_frontend_target(str(tmp_path)) == "mobile"


def test_android_manifest_returns_mobile(tmp_path):
    (tmp_path / "AndroidManifest.xml").write_text("<manifest/>")
    assert detect_frontend_target(str(tmp_path)) == "mobile"


def test_package_json_with_react_returns_web(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "^18"}}')
    assert detect_frontend_target(str(tmp_path)) == "web"


def test_package_json_with_next_returns_web(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"next": "^14"}}')
    assert detect_frontend_target(str(tmp_path)) == "web"


def test_cargo_toml_with_tauri_returns_desktop(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[dependencies]\ntauri = "1.0"')
    assert detect_frontend_target(str(tmp_path)) == "desktop"


def test_override_beats_tauri_conf(tmp_path):
    (tmp_path / "tauri.conf.json").write_text("{}")
    assert detect_frontend_target(str(tmp_path), override="mobile") == "mobile"


def test_empty_directory_returns_backend(tmp_path):
    assert detect_frontend_target(str(tmp_path)) == "backend"


def test_nonexistent_directory_returns_backend():
    assert detect_frontend_target("/tmp/this_path_does_not_exist_ever_12345") == "backend"


def test_malformed_package_json_returns_backend(tmp_path):
    (tmp_path / "package.json").write_bytes(b"\xff\xfe")  # invalid UTF-8
    assert detect_frontend_target(str(tmp_path)) == "backend"
