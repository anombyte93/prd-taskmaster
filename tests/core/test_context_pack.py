import json

from prd_taskmaster.context_pack import build_context_pack


def test_build_context_pack_extracts_classes_methods_functions_and_skips_broken_files(tmp_path):
    module = tmp_path / "sample.py"
    module.write_text(
        "\n".join(
            [
                "DEFAULT = 3",
                "",
                "class Worker:",
                "    \"\"\"Worker docs.",
                "",
                "    Extra details.",
                "    \"\"\"",
                "",
                "    def run(self, amount: int = DEFAULT, *, label: str = \"x\") -> str:",
                "        \"\"\"Run one job.",
                "",
                "        More docs.",
                "        \"\"\"",
                "        return label",
                "",
                "    async def fetch(self, url: str, /, timeout: float | None = None) -> bytes:",
                "        return b''",
                "",
                "def top_level(a, b: list[int] = [1, 2], *args: str, flag: bool = False, **kwargs) -> dict[str, int]:",
                "    \"\"\"Top level docs.\"\"\"",
                "    return {}",
            ]
        )
    )
    broken = tmp_path / "broken.py"
    broken.write_text("def nope(:\n")

    pack = build_context_pack([module, broken])

    assert pack == {
        "files": [
            {
                "path": str(module),
                "classes": [
                    {
                        "name": "Worker",
                        "methods": [
                            {
                                "name": "run",
                                "signature": "(self, amount: int = DEFAULT, *, label: str = \"x\") -> str",
                                "doc_first_line": "Run one job.",
                            },
                            {
                                "name": "fetch",
                                "signature": "(self, url: str, /, timeout: float | None = None) -> bytes",
                                "doc_first_line": "",
                            },
                        ],
                    }
                ],
                "functions": [
                    {
                        "name": "top_level",
                        "signature": "(a, b: list[int] = [1, 2], *args: str, flag: bool = False, **kwargs) -> dict[str, int]",
                        "doc_first_line": "Top level docs.",
                    }
                ],
            }
        ],
        "skipped": [str(broken)],
    }


def test_build_context_pack_filters_private_names_by_default_and_can_include_them(tmp_path):
    module = tmp_path / "private_sample.py"
    module.write_text(
        "\n".join(
            [
                "class Public:",
                "    def visible(self):",
                "        pass",
                "",
                "    def _hidden_method(self, value=1):",
                "        pass",
                "",
                "class _PrivateClass:",
                "    def visible(self):",
                "        pass",
                "",
                "def public_func():",
                "    pass",
                "",
                "def _private_func():",
                "    pass",
            ]
        )
    )

    filtered = build_context_pack([str(module)])
    assert filtered["files"][0]["classes"] == [
        {
            "name": "Public",
            "methods": [
                {
                    "name": "visible",
                    "signature": "(self)",
                    "doc_first_line": "",
                }
            ],
        }
    ]
    assert filtered["files"][0]["functions"] == [
        {"name": "public_func", "signature": "()", "doc_first_line": ""}
    ]

    unfiltered = build_context_pack([str(module)], include_private=True)
    assert [item["name"] for item in unfiltered["files"][0]["classes"]] == [
        "Public",
        "_PrivateClass",
    ]
    assert [item["name"] for item in unfiltered["files"][0]["classes"][0]["methods"]] == [
        "visible",
        "_hidden_method",
    ]
    assert [item["name"] for item in unfiltered["files"][0]["functions"]] == [
        "public_func",
        "_private_func",
    ]


def test_build_context_pack_result_is_json_serializable(tmp_path):
    module = tmp_path / "serializable.py"
    module.write_text("def f(x: int) -> int:\n    return x\n")

    assert json.loads(json.dumps(build_context_pack([module]))) == build_context_pack([module])
