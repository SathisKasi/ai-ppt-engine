# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules

block_cipher = None

def safe_copy_metadata(pkg_name):
    try:
        return copy_metadata(pkg_name)
    except Exception:
        return []

def safe_collect_data_files(pkg_name):
    try:
        return collect_data_files(pkg_name)
    except Exception:
        return []

# Explicitly collect project data assets
datas = [
    ('app.py', '.'),
    ('config.py', '.'),
    ('templates', 'templates'),
    ('.streamlit', '.streamlit'),
    ('TechM_RefPPT-V3.pptx', '.'),
    ('AITransformationWeeklyUpdate4SEP2026.pptx', '.'),
]

# Collect 3rd party package data files
datas += safe_collect_data_files('streamlit')
datas += safe_collect_data_files('pptx')
datas += safe_collect_data_files('pymupdf')
datas += safe_collect_data_files('pdfplumber')
datas += safe_collect_data_files('pypdfium2')
datas += safe_collect_data_files('ibm_watsonx_ai')

# Collect metadata (critical for runtime version checks)
datas += safe_copy_metadata('streamlit')
datas += safe_copy_metadata('altair')
datas += safe_copy_metadata('ibm_watsonx_ai')
datas += safe_copy_metadata('requests')
datas += safe_copy_metadata('pydantic')
datas += safe_copy_metadata('groq')

hiddenimports = [
    'streamlit',
    'streamlit.web.cli',
    'streamlit.web.bootstrap',
    'streamlit.runtime.scriptrunner.magic_expressions',
    'altair',
    'core',
    'core.content_analyzer',
    'core.document_parser',
    'core.document_structure',
    'core.layout_manager',
    'core.presentation_planner',
    'core.pptx_builder',
    'core.validator',
    'core.presentation_intelligence',
    'core.governance',
    'core.template_registry',
    'core.hld_qbr_catalog',
    'core.presentation_planner_hld_qbr_generic',
    'core.builders',
    'core.builders.dark_navy_builder',
    'core.builders.hld_qbr_builder',
    'core.builders.hld_qbr_generic_builder',
    'core.builders.techm_builder',
    'core.builders.techm_v3_builder',
    'core.builders.template1_builder',
    'core.builders.white_blue_builder',
    'llm',
    'llm.groq_client',
    'llm.watsonx_client',
    'llm.openrouter_client',
    'llm.key_manager',
    'llm.model_fallback',
    'llm.prompt_builder',
    'llm.token_tracker',
    'llm.hld_qbr_generic_schemas',
    'utils',
    'utils.logging_utils',
    'pptx',
    'ibm_watsonx_ai',
    'groq',
    'fitz',
    'pdfplumber',
    'pypdfium2',
    'docx',
    'openpyxl',
    'PIL',
    'lxml',
    'lxml.etree',
    'chardet',
    'pydeck',
    'pyarrow',
    'uvicorn',
    'starlette',
    'websockets',
]
hiddenimports += collect_submodules('streamlit')

a = Analysis(
    ['run_desktop.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'IPython',
        'notebook',
        'pytest',
        'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI-Presentation-Engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AI-Presentation-Engine',
)
