import os, sys
_venv = os.getenv("FoveAI_VENV_PATH", ".venv")
_venv_python = os.path.join(os.path.dirname(__file__), ".." if "/" in __file__ else "..", _venv, "Scripts", "python.exe")
if not os.path.exists(_venv_python):
    _venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", _venv, "Scripts", "python.exe")

"""
file_edit_buffer.py - Comprehensive file editing buffer with staging, validation, and review.
"""

import asyncio
import difflib
import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Set, Tuple, Callable

from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel, Field

from compactor import Compactor, node_registry


class EditType(Enum):
    CREATE = auto()
    MODIFY_LINE = auto()
    INSERT_LINES = auto()
    DELETE_LINES = auto()
    DELETE_FILE = auto()
    REPLACE_ALL = auto()


class EditStatus(Enum):
    PENDING = auto()
    VALIDATED = auto()
    APPROVED = auto()
    REJECTED = auto()
    COMMITTED = auto()
    DISCARDED = auto()


@dataclass
class LineEdit:
    line_number: int
    old_content: Optional[str]
    new_content: Optional[str]
    edit_type: EditType
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self):
        return {
            'line_number': self.line_number,
            'old_content': self.old_content,
            'new_content': self.new_content,
            'edit_type': self.edit_type.name,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class FileEdit:
    file_path: Path
    edits: List[LineEdit] = field(default_factory=list)
    status: EditStatus = EditStatus.PENDING
    original_hash: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)
    description: str = ''
    author: str = ''
    
    def add_edit(self, line_edit):
        self.edits.append(line_edit)
        self.modified_at = datetime.now()
        self.status = EditStatus.PENDING
    
    def get_edits_by_type(self, edit_type):
        return [e for e in self.edits if e.edit_type == edit_type]
    
    def to_dict(self):
        return {
            'file_path': str(self.file_path),
            'edits': [e.to_dict() for e in self.edits],
            'status': self.status.name,
            'original_hash': self.original_hash,
            'created_at': self.created_at.isoformat(),
            'modified_at': self.modified_at.isoformat(),
            'description': self.description,
            'author': self.author
        }


@dataclass
class ConflictWarning:
    severity: str
    message: str
    file_path: Optional[Path] = None
    line_number: Optional[int] = None
    suggestion: str = ''
    category: str = ''
    
    def to_dict(self):
        return {
            'severity': self.severity,
            'message': self.message,
            'file_path': str(self.file_path) if self.file_path else None,
            'line_number': self.line_number,
            'suggestion': self.suggestion,
            'category': self.category
        }


class FileEditBuffer:
    def __init__(self, file_path, base_path=None):
        self.file_path = Path(file_path)
        self.base_path = base_path
        self.file_edit = FileEdit(file_path=self.file_path)
        self._original_content = None
        self._original_hash = None
        self._is_new_file = not self.file_path.exists()
        if not self._is_new_file:
            self._load_original()
    
    def _load_original(self):
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self._original_content = content.splitlines(keepends=True)
                self._original_hash = hashlib.sha256(content.encode()).hexdigest()
                self.file_edit.original_hash = self._original_hash
        except Exception:
            self._original_content = []
            self._original_hash = None
    
    def stage_create(self, content, description='', author=''):
        edit = LineEdit(line_number=0, old_content=None, new_content=content, edit_type=EditType.CREATE)
        self.file_edit.add_edit(edit)
        self.file_edit.description = description
        self.file_edit.author = author
        return edit
    
    def stage_modify_line(self, line_number, new_content):
        old_content = None
        if self._original_content and 0 <= line_number < len(self._original_content):
            old_content = self._original_content[line_number].rstrip('\n\r')
        edit = LineEdit(line_number=line_number, old_content=old_content, new_content=new_content, edit_type=EditType.MODIFY_LINE)
        self.file_edit.add_edit(edit)
        return edit
    
    def stage_insert_lines(self, line_number, lines):
        content = '\n'.join(lines)
        edit = LineEdit(line_number=line_number, old_content=None, new_content=content, edit_type=EditType.INSERT_LINES)
        self.file_edit.add_edit(edit)
        return edit
    
    def stage_delete_lines(self, start_line, end_line):
        old_content = None
        if self._original_content:
            lines_to_delete = self._original_content[start_line:end_line+1]
            old_content = ''.join(lines_to_delete)
        edit = LineEdit(line_number=start_line, old_content=old_content, new_content=None, edit_type=EditType.DELETE_LINES)
        self.file_edit.add_edit(edit)
        return edit
    
    def stage_delete_file(self):
        edit = LineEdit(line_number=0, old_content=None, new_content=None, edit_type=EditType.DELETE_FILE)
        self.file_edit.add_edit(edit)
        return edit
    
    def stage_replace_all(self, new_content):
        old_content = None
        if self._original_content:
            old_content = ''.join(self._original_content)
        edit = LineEdit(line_number=0, old_content=old_content, new_content=new_content, edit_type=EditType.REPLACE_ALL)
        self.file_edit.add_edit(edit)
        return edit
    
    def generate_diff(self):
        original = self._original_content or []
        new_content = self.get_staged_content()
        original_str = ''.join(original)
        new_str = new_content if isinstance(new_content, str) else ''.join(new_content)
        diff = difflib.unified_diff(
            original_str.splitlines(keepends=True),
            new_str.splitlines(keepends=True),
            fromfile=str(self.file_path),
            tofile=str(self.file_path) + '.staged',
            lineterm=''
        )
        return ''.join(diff)
    
    def _apply_edits_to_lines(self, edits):
        if not self._original_content:
            return []
        lines = self._original_content.copy()
        sorted_edits = sorted(edits, key=lambda e: e.line_number, reverse=True)
        for edit in sorted_edits:
            if edit.edit_type == EditType.MODIFY_LINE:
                if 0 <= edit.line_number < len(lines):
                    lines[edit.line_number] = edit.new_content + '\n'
            elif edit.edit_type == EditType.INSERT_LINES:
                new_lines = edit.new_content.split('\n') if edit.new_content else []
                for i, line in enumerate(new_lines):
                    lines.insert(edit.line_number + i, line + '\n')
            elif edit.edit_type == EditType.DELETE_LINES:
                del lines[edit.line_number:edit.line_number + 1]
            elif edit.edit_type == EditType.REPLACE_ALL:
                return edit.new_content.splitlines(keepends=True) if edit.new_content else []
        return lines
    
    def get_staged_content(self):
        if not self.file_edit.edits:
            return self._original_content or []
        for edit in reversed(self.file_edit.edits):
            if edit.edit_type == EditType.CREATE:
                return edit.new_content or ''
            elif edit.edit_type == EditType.REPLACE_ALL:
                return edit.new_content or ''
            elif edit.edit_type == EditType.DELETE_FILE:
                return []
        lines = self._apply_edits_to_lines(self.file_edit.edits)
        return lines
    
    def clear(self):
        self.file_edit.edits = []
        self.file_edit.status = EditStatus.PENDING
    
    def get_edit_summary(self):
        summary = {edit_type.name: 0 for edit_type in EditType}
        for edit in self.file_edit.edits:
            summary[edit.edit_type.name] += 1
        return summary
    
    def has_conflicts(self):
        conflicts = []
        line_edits = {}
        for edit in self.file_edit.edits:
            if edit.line_number not in line_edits:
                line_edits[edit.line_number] = []
            line_edits[edit.line_number].append(edit)
        for line_num, edits in line_edits.items():
            if len(edits) > 1:
                types = [e.edit_type.name for e in edits]
                conflicts.append(f"Line {line_num}: multiple edits ({', '.join(types)})")
        return len(conflicts) > 0, conflicts


class LibrarianReview:
    def __init__(self, history_file=None):
        self.history_file = history_file or Path('.librarian_history.json')
        self.edit_history = []
        self._load_history()
        self._patterns = {}
        self._register_default_patterns()
    
    def _register_default_patterns(self):
        self._patterns['todo_marker'] = self._check_todo_markers
        self._patterns['debug_print'] = self._check_debug_statements
        self._patterns['merge_conflict'] = self._check_merge_conflict_markers
    
    def _check_todo_markers(self, content, file_path):
        if 'TODO' in content or 'FIXME' in content:
            return ConflictWarning(severity='info', message='File contains TODO/FIXME markers', file_path=file_path, suggestion='Review and complete or remove TODO items before committing', category='pattern')
        return None
    
    def _check_debug_statements(self, content, file_path):
        if file_path.suffix == '.py':
            if re.search(r'print\s*\(|pprint\s*\(|console\.log', content):
                return ConflictWarning(severity='warning', message='Debug print statements detected', file_path=file_path, suggestion='Remove debug statements before production commit', category='pattern')
        return None
    
    def _check_merge_conflict_markers(self, content, file_path):
        if '<<<<<<<' in content and '=======' in content and '>>>>>>>' in content:
            return ConflictWarning(severity='critical', message='Unresolved merge conflict markers detected', file_path=file_path, suggestion='Resolve merge conflicts before committing', category='conflict')
        return None
    
    def _load_history(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    self.edit_history = json.load(f)
            except Exception:
                self.edit_history = []
    
    def _save_history(self):
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.edit_history, f, indent=2, default=str)
        except Exception:
            pass
    
    def _check_historical_conflicts(self, file_path):
        warnings = []
        recent_edits = [h for h in self.edit_history[-20:] if h.get('file_path') == str(file_path)]
        if len(recent_edits) > 5:
            warnings.append(ConflictWarning(severity='warning', message=f'File has been edited {len(recent_edits)} times recently', file_path=file_path, suggestion='Consider if changes are being iterative; may need consolidation', category='pattern'))
        return warnings
    
    def _check_missing_dependencies(self, content, file_path):
        warnings = []
        if file_path.suffix == '.py':
            import_pattern = r'^(?:from|import)\s+(\w+)'
            imports = re.findall(import_pattern, content, re.MULTILINE)
            common_stdlib = {'os', 'sys', 'json', 're', 'datetime', 'pathlib', 'typing', 'collections'}
            for imp in imports:
                if imp not in common_stdlib:
                    warnings.append(ConflictWarning(severity='info', message=f'External dependency: {imp}', file_path=file_path, suggestion='Ensure dependency is in requirements.txt or pyproject.toml', category='dependency'))
        return warnings
    
    def _check_common_patterns(self, content, file_path):
        warnings = []
        for name, checker in self._patterns.items():
            result = checker(content, file_path)
            if result:
                warnings.append(result)
        return warnings
    
    def review(self, file_edit, staged_content=None):
        warnings = []
        if staged_content is None:
            if file_edit.file_path.exists():
                try:
                    with open(file_edit.file_path, 'r') as f:
                        staged_content = f.read()
                except Exception:
                    staged_content = ''
            else:
                staged_content = ''
        warnings.extend(self._check_historical_conflicts(file_edit.file_path))
        warnings.extend(self._check_missing_dependencies(staged_content, file_edit.file_path))
        warnings.extend(self._check_common_patterns(staged_content, file_edit.file_path))
        if not file_edit.description:
            warnings.append(ConflictWarning(severity='info', message='Edit lacks a description', suggestion='Add a description to help track changes', category='pattern'))
        severity_counts = {'critical': 0, 'error': 0, 'warning': 0, 'info': 0}
        for w in warnings:
            severity_counts[w.severity] = severity_counts.get(w.severity, 0) + 1
        approved = severity_counts['critical'] == 0 and severity_counts['error'] == 0
        return {'approved': approved, 'warnings': [w.to_dict() for w in warnings], 'severity_counts': severity_counts, 'total_issues': len(warnings), 'recommendation': 'approve' if approved else 'reject'}
    
    def record_session(self, file_edits, committed=True):
        session = {'timestamp': datetime.now().isoformat(), 'committed': committed, 'files': [edit.to_dict() for edit in file_edits]}
        self.edit_history.append(session)
        self._save_history()


class ValidationError(Exception):
    pass


class FileValidator:
    def __init__(self, base_path=None):
        self.base_path = base_path or Path.cwd()
        self.protected_paths = set()
        self.required_patterns = []
        self.forbidden_patterns = [r'__pycache__', r'\.git', r'\.venv', r'\.env', r'\.log$']
    
    def add_protected_path(self, path):
        self.protected_paths.add(Path(path).resolve())
    
    def add_required_pattern(self, pattern):
        self.required_patterns.append(pattern)
    
    def validate_file_path(self, file_path):
        path = Path(file_path).resolve()
        errors = []
        try:
            path.relative_to(self.base_path)
        except ValueError:
            errors.append(f'Path {path} is outside base directory {self.base_path}')
        for protected in self.protected_paths:
            if path == protected or protected in path.parents:
                errors.append(f'Path {path} is protected')
        for pattern in self.forbidden_patterns:
            if re.search(pattern, str(path)):
                errors.append(f'Path matches forbidden pattern: {pattern}')
        if '..' in str(path):
            errors.append('Path contains traversal characters')
        return len(errors) == 0, errors
    
    def validate_edit(self, file_edit):
        valid, errors = self.validate_file_path(file_edit.file_path)
        if not valid:
            return False, errors
        for edit in file_edit.edits:
            if edit.edit_type == EditType.DELETE_FILE:
                if file_edit.file_path in self.protected_paths:
                    errors.append(f'Cannot delete protected file: {file_edit.file_path}')
        return len(errors) == 0, errors
    
    def validate_content_safety(self, content, file_path):
        errors = []
        if file_path.suffix in ['.txt', '.md', '.json']:
            dangerous_patterns = [r'#!/bin/bash', r'#!/bin/sh', r'eval\s*\(', r'exec\s*\(', r'subprocess\.call', r'os\.system']
            for pattern in dangerous_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    errors.append(f'Potentially dangerous pattern detected: {pattern}')
        lines = content.split('\n')
        long_lines = [i for i, line in enumerate(lines, 1) if len(line) > 500]
        if long_lines:
            errors.append(f'Lines with excessive length: {long_lines}')
        if '\x00' in content:
            errors.append('Content contains null bytes')
        return len(errors) == 0, errors


class StagingArea:
    def __init__(self, base_path=None):
        self.base_path = base_path or Path.cwd()
        self.buffers = {}
        self.validator = FileValidator(base_path=self.base_path)
        self.librarian = LibrarianReview()
        self.backup_dir = None
        self._backup_created = False
    
    def _ensure_backup(self):
        if not self._backup_created:
            self.backup_dir = self.base_path / '.staging_backups'
            self.backup_dir.mkdir(exist_ok=True)
            self._backup_created = True
    
    def stage_file(self, file_path):
        path = Path(file_path).resolve()
        if path not in self.buffers:
            self.buffers[path] = FileEditBuffer(path, base_path=self.base_path)
        return self.buffers[path]
    
    def stage_create_file(self, file_path, content, description='', author=''):
        path = Path(file_path).resolve()
        valid, errors = self.validator.validate_file_path(path)
        if not valid:
            raise ValidationError(f"Cannot stage file: {', '.join(errors)}")
        buffer = self.stage_file(path)
        buffer.stage_create(content, description=description, author=author)
        return buffer
    
    def stage_modify_lines(self, file_path, line_changes):
        path = Path(file_path).resolve()
        buffer = self.stage_file(path)
        for line_num, new_content in line_changes:
            buffer.stage_modify_line(line_num, new_content)
        return buffer
    
    def stage_insert_lines(self, file_path, position, lines):
        path = Path(file_path).resolve()
        buffer = self.stage_file(path)
        buffer.stage_insert_lines(position, lines)
        return buffer
    
    def stage_delete_lines(self, file_path, start_line, end_line):
        path = Path(file_path).resolve()
        buffer = self.stage_file(path)
        buffer.stage_delete_lines(start_line, end_line)
        return buffer
    
    def preview_changes(self, file_path=None):
        if file_path:
            path = Path(file_path).resolve()
            if path in self.buffers:
                buffer = self.buffers[path]
                return {'file': str(path), 'diff': buffer.generate_diff(), 'edit_summary': buffer.get_edit_summary(), 'conflicts': buffer.has_conflicts()[1]}
            return {'error': f'File not staged: {path}'}
        previews = {}
        for path, buffer in self.buffers.items():
            has_conflict, conflicts = buffer.has_conflicts()
            previews[str(path)] = {'diff': buffer.generate_diff(), 'edit_summary': buffer.get_edit_summary(), 'has_conflicts': has_conflict, 'conflicts': conflicts}
        return {'total_files': len(self.buffers), 'files': previews}
    
    def librarian_review(self):
        all_reviews = {}
        for path, buffer in self.buffers.items():
            review = self.librarian.review(buffer.file_edit)
            all_reviews[str(path)] = review
        total_warnings = sum(r['total_issues'] for r in all_reviews.values())
        can_commit = all(r['approved'] for r in all_reviews.values())
        return {'can_commit': can_commit, 'total_warnings': total_warnings, 'file_reviews': all_reviews}
    
    def commit_all(self, create_backups=True):
        results = {'committed': [], 'failed': [], 'backups': []}
        if create_backups:
            self._ensure_backup()
        for path, buffer in list(self.buffers.items()):
            try:
                valid, errors = self.validator.validate_edit(buffer.file_edit)
                if not valid:
                    results['failed'].append({'file': str(path), 'error': errors})
                    continue
                if create_backups and path.exists():
                    backup_path = self.backup_dir / f'{path.name}.{datetime.now().strftime("%Y%m%d_%H%M%S")}.bak'
                    shutil.copy2(path, backup_path)
                    results['backups'].append(str(backup_path))
                content = buffer.get_staged_content()
                if isinstance(content, list):
                    content = ''.join(content)
                
                # Expand any compact skeletons before committing to disk
                from compactor import Compactor
                compactor = Compactor()
                content = compactor.expand_skeleton(content)
                
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                buffer.file_edit.status = EditStatus.COMMITTED
                results['committed'].append(str(path))
            except Exception as e:
                results['failed'].append({'file': str(path), 'error': str(e)})
        self.librarian.record_session([b.file_edit for b in self.buffers.values()], committed=len(results['failed']) == 0)
        if len(results['failed']) == 0:
            self._clear_staging()
        return results
    
    def discard_all(self):
        self._clear_staging()
    
    def _clear_staging(self):
        for buffer in self.buffers.values():
            buffer.file_edit.status = EditStatus.DISCARDED
        self.buffers = {}
    
    def get_status(self):
        return {'staged_files': len(self.buffers), 'files': [str(p) for p in self.buffers.keys()], 'total_edits': sum(len(b.file_edit.edits) for b in self.buffers.values()), 'backup_dir': str(self.backup_dir) if self.backup_dir else None}


class StageEditRequest(BaseModel):
    file_path: str = Field(..., description='Path to the file to edit')
    edit_type: str = Field(..., description='Type of edit: create, modify, insert, delete, delete_file, replace')
    content: Optional[str] = Field(None, description='Content for create/modify/replace operations')
    line_number: Optional[int] = Field(None, description='Line number for modify/insert operations')
    end_line: Optional[int] = Field(None, description='End line for delete range')
    lines: Optional[List[str]] = Field(None, description='Lines to insert')
    description: str = Field('', description='Description of the edit')
    author: str = Field('', description='Author of the edit')


class StageCreateRequest(BaseModel):
    file_path: str = Field(..., description='Path to the new file')
    content: str = Field(..., description='File content')
    description: str = Field('', description='Description')
    author: str = Field('', description='Author')


class ModifyLinesRequest(BaseModel):
    file_path: str = Field(..., description='Path to the file')
    changes: List[Tuple[int, str]] = Field(..., description='List of (line_number, new_content) tuples')


class NodePatchRequest(BaseModel):
    node_id: str = Field(..., description="The unique hash ID of the node to patch")
    new_content: str = Field(..., description="The replacement content for the node body")
    description: str = Field('', description='Description of the edit')
    author: str = Field('', description='Author of the edit')


class CompactRequest(BaseModel):
    file_path: str = Field(..., description="Path to the file to compact")


def create_edit_router(staging_area=None):
    router = APIRouter(prefix='/edits', tags=['file-edits'])
    staging = staging_area or StagingArea()
    
    @router.post('/stage')
    async def stage_edit(request: StageEditRequest):
        try:
            edit_type = request.edit_type.lower()
            buffer = staging.stage_file(request.file_path)
            if edit_type == 'create':
                buffer.stage_create(request.content or '', request.description, request.author)
            elif edit_type == 'modify':
                if request.line_number is None:
                    raise HTTPException(status_code=400, detail='line_number required for modify')
                buffer.stage_modify_line(request.line_number, request.content or '')
            elif edit_type == 'insert':
                if request.line_number is None or request.lines is None:
                    raise HTTPException(status_code=400, detail='line_number and lines required for insert')
                buffer.stage_insert_lines(request.line_number, request.lines)
            elif edit_type == 'delete':
                if request.line_number is None:
                    raise HTTPException(status_code=400, detail='line_number required for delete')
                end = request.end_line or request.line_number
                buffer.stage_delete_lines(request.line_number, end)
            elif edit_type == 'delete_file':
                buffer.stage_delete_file()
            elif edit_type == 'replace':
                buffer.stage_replace_all(request.content or '')
            else:
                raise HTTPException(status_code=400, detail=f'Unknown edit type: {edit_type}')
            return {'status': 'staged', 'file': request.file_path, 'edit_type': edit_type}
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post('/compact')
    async def compact_file(request: CompactRequest):
        try:
            path = Path(request.file_path).resolve()
            if not path.exists():
                raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
            
            if path in staging.buffers:
                content = staging.buffers[path].get_staged_content()
                if isinstance(content, list):
                    content = "".join(content)
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
            compactor = Compactor()
            compacted = compactor.compact(path, content)
            
            buffer = staging.stage_file(path)
            buffer.stage_replace_all(compacted)
            
            return {
                "status": "compacted_and_staged",
                "file_path": str(path),
                "original_length": len(content),
                "compacted_length": len(compacted),
                "skeleton": compacted
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post('/expand')
    async def expand_file(request: CompactRequest):
        try:
            path = Path(request.file_path).resolve()
            if not path.exists():
                raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
            
            if path in staging.buffers:
                content = staging.buffers[path].get_staged_content()
                if isinstance(content, list):
                    content = "".join(content)
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
            compactor = Compactor()
            expanded = compactor.expand_skeleton(content)
            
            buffer = staging.stage_file(path)
            buffer.stage_replace_all(expanded)
            
            return {
                "status": "expanded_and_staged",
                "file_path": str(path),
                "original_length": len(content),
                "expanded_length": len(expanded)
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get('/nodes/{node_id}')
    async def get_node(node_id: str):
        node = node_registry.get(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found in registry")
        return node

    @router.post('/nodes/patch')
    async def patch_node(request: NodePatchRequest):
        try:
            node_info = node_registry.get(request.node_id)
            if not node_info:
                raise HTTPException(status_code=404, detail=f"Node {request.node_id} not found in registry")
                
            path = Path(node_info["file_path"])
            
            if path in staging.buffers:
                content = staging.buffers[path].get_staged_content()
                if isinstance(content, list):
                    content = "".join(content)
            else:
                if not path.exists():
                    raise HTTPException(status_code=404, detail=f"File {path} does not exist")
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            py_placeholder_pattern = rf"[ \t]*# NODE:{request.node_id}(?:\n[ \t]*pass)?"
            js_placeholder_pattern = rf"/\*\s*NODE:{request.node_id}\s*\*/"
            
            patched_content = None
            
            if re.search(py_placeholder_pattern, content):
                match = re.search(r"([ \t]*)# NODE:" + request.node_id, content)
                indent = match.group(1) if match else ""
                
                indented_lines = []
                for line in request.new_content.splitlines(keepends=True):
                    indented_lines.append(indent + line)
                indented_new_content = "".join(indented_lines)
                
                patched_content = re.sub(py_placeholder_pattern, indented_new_content, content, count=1)
                
            elif re.search(js_placeholder_pattern, content):
                patched_content = re.sub(js_placeholder_pattern, request.new_content, content, count=1)
                
            elif node_info["original_content"] in content:
                patched_content = content.replace(node_info["original_content"], request.new_content, 1)
                
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not locate node {request.node_id} (or its original content) in the file."
                )
                
            buffer = staging.stage_file(path)
            buffer.stage_replace_all(patched_content)
            
            if request.description:
                buffer.file_edit.description = request.description
            if request.author:
                buffer.file_edit.author = request.author
                
            return {
                "status": "patched_and_staged",
                "file_path": str(path),
                "node_id": request.node_id
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get('/preview')
    async def preview_changes(file_path: str = None):
        return staging.preview_changes(Path(file_path) if file_path else None)
    
    @router.post('/commit')
    async def commit_changes(create_backups: bool = True):
        return staging.commit_all(create_backups=create_backups)
    
    @router.post('/discard')
    async def discard_changes():
        staging.discard_all()
        return {'status': 'discarded', 'message': 'All staged changes have been discarded'}
    
    @router.get('/librarian-review')
    async def librarian_review():
        return staging.librarian_review()
    
    @router.get('/status')
    async def get_status():
        return staging.get_status()
    
    return router


def create_edit_app(staging_area=None):
    app = FastAPI(title='File Edit Buffer API', description='API for staging and managing file edits', version='1.0.0')
    router = create_edit_router(staging_area)
    app.include_router(router)
    
    @app.get('/health')
    async def health_check():
        return {'status': 'healthy', 'service': 'file-edit-buffer'}
    
    return app


def example_workflow():
    print('=' * 60)
    print('FILE EDIT BUFFER - Example Workflow')
    print('=' * 60)
    staging = StagingArea()
    print('\n1. Creating a new file...')
    try:
        buffer = staging.stage_create_file('example_new.py', '# New Python file\nprint("Hello World")\n', description='Create example file', author='Demo User')
        print(f'   Staged: {buffer.file_path}')
    except ValidationError as e:
        print(f'   Error: {e}')
    print('\n2. Previewing changes...')
    preview = staging.preview_changes()
    print(f'   Total files staged: {preview["total_files"]}')
    print('\n3. Running librarian review...')
    review = staging.librarian_review()
    print(f'   Can commit: {review["can_commit"]}')
    print(f'   Total warnings: {review["total_warnings"]}')
    print('\n4. Checking status...')
    status = staging.get_status()
    print(f'   Staged files: {status["staged_files"]}')
    print(f'   Files: {status["files"]}')
    print('\n5. Discarding changes...')
    staging.discard_all()
    print('   All changes discarded')
    print('\n' + '=' * 60)
    print('Workflow complete!')
    print('=' * 60)


if __name__ == '__main__':
    example_workflow()
