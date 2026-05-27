from pathlib import Path
import setuptools


HERE = Path(__file__).parent


def read_long_description() -> str:
    try:
        return (HERE / "README.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        return "paper2repro — self-hosted multi-agent server for paper reproduction"


def read_requirements() -> list[str]:
    try:
        text = (HERE / "requirements.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


setuptools.setup(
    name="paper2repro",
    version="0.1.0",
    author="shiqirui",
    description=(
        "Self-hosted multi-agent server for paper reproduction. "
        "Part of the Papyrus suite. Fork of HKUDS/DeepCode."
    ),
    long_description=read_long_description(),
    long_description_content_type="text/markdown",
    license="MIT",
    packages=setuptools.find_packages(
        exclude=(
            "tests*",
            "docs*",
            ".history*",
            ".git*",
            ".ruff_cache*",
            "frontend*",
            "demo*",
            "datasets*",
            "output*",
            "papers*",
            "scripts*",
        )
    ),
    py_modules=["paper2repro"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Text Processing :: Linguistic",
    ],
    python_requires=">=3.9",
    install_requires=read_requirements(),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "paper2repro=paper2repro:main",
        ],
    },
)
