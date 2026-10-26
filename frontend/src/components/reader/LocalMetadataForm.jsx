import React, { useEffect, useRef, useState } from 'react';
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { PRIORITIES, LOCAL_STATUSES } from './classification';

/**
 * Edits the application's own classification for a page.
 *
 * This writes to the local metadata store (PUT /api/spaces/:key/pages/:id/metadata)
 * and never touches Confluence — which is why the action is called "Edit local
 * metadata" and the form says so explicitly.
 */
export default function LocalMetadataForm({ page, onSave, onCancel, saving, error }) {
  const [fields, setFields] = useState({
    priority: page.priority || '',
    domain: page.domain || '',
    team: page.team || '',
    owner: page.owner || '',
    reviewer: page.reviewer || '',
    local_status: page.local_status || 'imported',
    notes: page.notes || '',
  });
  const firstFieldRef = useRef(null);

  useEffect(() => {
    firstFieldRef.current?.focus();
  }, []);

  const set = (key) => (event) =>
    setFields((prev) => ({ ...prev, [key]: event.target.value }));

  const submit = (event) => {
    event.preventDefault();
    onSave(fields);
  };

  return (
    <form className="rd-panel" onSubmit={submit} aria-labelledby="edit-metadata-heading">
      <h2 className="rd-panel-head" id="edit-metadata-heading">Edit local metadata</h2>
      <div className="rd-panel-body">
        <p style={{ margin: '0 0 0.875rem', fontSize: 'var(--rd-fs-meta)',
                    color: 'var(--rd-text-secondary)' }}>
          These fields are stored in this application only. Saving does not
          change the page in Confluence.
        </p>

        <div style={{ display: 'grid', gap: '0.75rem' }}>
          <label style={{ fontSize: 'var(--rd-fs-meta)', color: 'var(--rd-text)' }}>
            Priority
            <select ref={firstFieldRef} className="input-field" value={fields.priority}
                    onChange={set('priority')} style={{ marginTop: '0.25rem' }}>
              <option value="">Not set</option>
              {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>

          <label style={{ fontSize: 'var(--rd-fs-meta)', color: 'var(--rd-text)' }}>
            Domain
            <input className="input-field" value={fields.domain} onChange={set('domain')}
                   style={{ marginTop: '0.25rem' }} placeholder="Not set" />
          </label>

          <label style={{ fontSize: 'var(--rd-fs-meta)', color: 'var(--rd-text)' }}>
            Team
            <input className="input-field" value={fields.team} onChange={set('team')}
                   style={{ marginTop: '0.25rem' }} placeholder="Unassigned" />
          </label>

          <label style={{ fontSize: 'var(--rd-fs-meta)', color: 'var(--rd-text)' }}>
            Owner
            <input className="input-field" value={fields.owner} onChange={set('owner')}
                   style={{ marginTop: '0.25rem' }} placeholder="Unassigned" />
          </label>

          <label style={{ fontSize: 'var(--rd-fs-meta)', color: 'var(--rd-text)' }}>
            Reviewer
            <input className="input-field" value={fields.reviewer} onChange={set('reviewer')}
                   style={{ marginTop: '0.25rem' }} placeholder="Unassigned" />
          </label>

          <label style={{ fontSize: 'var(--rd-fs-meta)', color: 'var(--rd-text)' }}>
            Local status
            <select className="input-field" value={fields.local_status}
                    onChange={set('local_status')} style={{ marginTop: '0.25rem' }}>
              {LOCAL_STATUSES.map((s) => (
                <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </label>

          <label style={{ fontSize: 'var(--rd-fs-meta)', color: 'var(--rd-text)' }}>
            Notes
            <textarea className="input-field" value={fields.notes} onChange={set('notes')}
                      rows={3} style={{ marginTop: '0.25rem', resize: 'vertical' }}
                      placeholder="Local notes" />
          </label>
        </div>

        {error ? (
          <p role="alert" style={{ margin: '0.75rem 0 0', fontSize: 'var(--rd-fs-meta)',
                                   color: 'var(--rd-danger-text)' }}>
            {error}
          </p>
        ) : null}

        <div className="rd-actions">
          <button type="submit" className="btn-primary" disabled={saving}>
            <CheckIcon aria-hidden="true" className="h-4 w-4" />
            {saving ? 'Saving…' : 'Save local metadata'}
          </button>
          <button type="button" className="btn-ghost" onClick={onCancel} disabled={saving}>
            <XMarkIcon aria-hidden="true" className="h-4 w-4" />
            Cancel
          </button>
        </div>
      </div>
    </form>
  );
}
