import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * dashboard/src/components/ingestion/NewJobForm.tsx
 *
 * New in Phase 9. schemas/ingest.py's IngestJobCreate requires an
 * explicit `documents: DocumentRef[]` (source_path/document_type/
 * patient_id per document, 1–5000 items) — a real API-shape divergence
 * from the original doc-32 sketch's single S3-prefix field (see that
 * schema's own docstring). A single text input can't express that, so
 * this form offers two entry modes for the same underlying `documents`
 * state:
 *   - Manual rows: add/remove one DocumentRef at a time — practical for
 *     a handful of documents.
 *   - Paste JSON: a textarea accepting a raw JSON array of
 *     `{ source_path, document_type, patient_id }` objects, parsed and
 *     validated client-side into the same rows — practical for anything
 *     larger. A manifest-file-upload endpoint was flagged in that same
 *     schema docstring as a "Phase 4+ enhancement, not blocking" and
 *     still doesn't exist, so this is the bulk path until it does.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { DOCUMENT_TYPES, useCreateJob, } from '../../hooks/useIngestionJobs';
import { getApiErrorMessage } from '../../lib/api';
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_DOCUMENTS = 5000;
function emptyRow() {
    return { source_path: '', document_type: 'clinical_note', patient_id: '' };
}
export function NewJobForm() {
    const navigate = useNavigate();
    const createJob = useCreateJob();
    const [name, setName] = useState('');
    const [chunkSize, setChunkSize] = useState(512);
    const [chunkOverlap, setChunkOverlap] = useState(50);
    const [rows, setRows] = useState([emptyRow()]);
    const [mode, setMode] = useState('manual');
    const [jsonText, setJsonText] = useState('');
    const [jsonError, setJsonError] = useState(null);
    function updateRow(index, patch) {
        setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
    }
    function addRow() {
        setRows((prev) => (prev.length >= MAX_DOCUMENTS ? prev : [...prev, emptyRow()]));
    }
    function removeRow(index) {
        setRows((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== index)));
    }
    function applyJson() {
        setJsonError(null);
        try {
            const parsed = JSON.parse(jsonText);
            if (!Array.isArray(parsed))
                throw new Error('Expected a JSON array of documents');
            if (parsed.length === 0)
                throw new Error('Array is empty');
            if (parsed.length > MAX_DOCUMENTS)
                throw new Error(`Max ${MAX_DOCUMENTS} documents per job`);
            const valid = parsed.map((item, i) => {
                const o = item;
                if (!o.source_path || typeof o.source_path !== 'string') {
                    throw new Error(`Row ${i + 1}: missing source_path`);
                }
                if (!o.document_type || !DOCUMENT_TYPES.includes(o.document_type)) {
                    throw new Error(`Row ${i + 1}: document_type must be one of ${DOCUMENT_TYPES.join(', ')}`);
                }
                if (!o.patient_id || typeof o.patient_id !== 'string') {
                    throw new Error(`Row ${i + 1}: missing patient_id`);
                }
                return { source_path: o.source_path, document_type: o.document_type, patient_id: o.patient_id };
            });
            setRows(valid);
            setMode('manual');
        }
        catch (err) {
            setJsonError(err instanceof Error ? err.message : 'Invalid JSON');
        }
    }
    const nameValid = name.trim().length > 0 && name.length <= 200;
    const rowsValid = rows.length > 0 &&
        rows.length <= MAX_DOCUMENTS &&
        rows.every((r) => r.source_path.trim() && r.patient_id.trim());
    const chunkValid = chunkSize >= 64 && chunkSize <= 2048 && chunkOverlap >= 0 && chunkOverlap <= 256;
    const formValid = nameValid && rowsValid && chunkValid;
    async function onSubmit(e) {
        e.preventDefault();
        if (!formValid)
            return;
        const payload = {
            name: name.trim(),
            documents: rows.map((r) => ({ ...r, source_path: r.source_path.trim(), patient_id: r.patient_id.trim() })),
            chunk_size: chunkSize,
            chunk_overlap: chunkOverlap,
        };
        const job = await createJob.mutateAsync(payload);
        navigate(`/ingestion?highlight=${job.jobId}`);
    }
    return (_jsxs("form", { className: "new-job-form", onSubmit: onSubmit, children: [_jsxs("label", { className: "field", children: [_jsx("span", { className: "field-label", children: "Job name" }), _jsx("input", { value: name, onChange: (e) => setName(e.target.value), maxLength: 200, placeholder: "nightly-clinical-notes-2026-08" })] }), _jsxs("div", { className: "field-row", children: [_jsxs("label", { className: "field", children: [_jsx("span", { className: "field-label", children: "Chunk size (chars)" }), _jsx("input", { type: "number", min: 64, max: 2048, value: chunkSize, onChange: (e) => setChunkSize(Number(e.target.value)) })] }), _jsxs("label", { className: "field", children: [_jsx("span", { className: "field-label", children: "Chunk overlap (chars)" }), _jsx("input", { type: "number", min: 0, max: 256, value: chunkOverlap, onChange: (e) => setChunkOverlap(Number(e.target.value)) })] })] }), _jsxs("div", { className: "new-job-mode-toggle", children: [_jsxs("button", { type: "button", className: mode === 'manual' ? 'tab-btn active' : 'tab-btn', onClick: () => setMode('manual'), children: ["Manual rows (", rows.length, ")"] }), _jsx("button", { type: "button", className: mode === 'json' ? 'tab-btn active' : 'tab-btn', onClick: () => setMode('json'), children: "Paste JSON" })] }), mode === 'manual' ? (_jsxs("div", { className: "doc-rows", children: [rows.map((row, i) => (_jsxs("div", { className: "doc-row", children: [_jsx("input", { className: "doc-row-path", placeholder: "r2://pvh-documents-dev/raw/...", value: row.source_path, onChange: (e) => updateRow(i, { source_path: e.target.value }) }), _jsx("select", { value: row.document_type, onChange: (e) => updateRow(i, { document_type: e.target.value }), children: DOCUMENT_TYPES.map((t) => (_jsx("option", { value: t, children: t }, t))) }), _jsx("input", { className: "doc-row-patient mono", placeholder: "patient UUID", value: row.patient_id, onChange: (e) => updateRow(i, { patient_id: e.target.value }), style: row.patient_id && !UUID_RE.test(row.patient_id) ? { borderColor: 'var(--color-warning)' } : undefined }), _jsx("button", { type: "button", className: "btn-icon", onClick: () => removeRow(i), disabled: rows.length <= 1, "aria-label": "Remove row", children: "\u2715" })] }, i))), _jsx("button", { type: "button", className: "btn-ghost", onClick: addRow, disabled: rows.length >= MAX_DOCUMENTS, children: "+ Add document" })] })) : (_jsxs("div", { className: "json-paste", children: [_jsx("textarea", { rows: 10, placeholder: '[\n  { "source_path": "r2://...", "document_type": "clinical_note", "patient_id": "..." }\n]', value: jsonText, onChange: (e) => setJsonText(e.target.value) }), jsonError && _jsx("p", { className: "field-error", children: jsonError }), _jsx("button", { type: "button", className: "btn-ghost", onClick: applyJson, children: "Apply to rows" })] })), createJob.isError && _jsx("p", { className: "field-error", children: getApiErrorMessage(createJob.error) }), _jsx("button", { type: "submit", className: "btn-primary", disabled: !formValid || createJob.isPending, children: createJob.isPending ? 'Submitting…' : `Start ingestion (${rows.length} document${rows.length === 1 ? '' : 's'})` })] }));
}
