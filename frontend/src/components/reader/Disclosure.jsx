import React, { useId, useState } from 'react';
import { ChevronDownIcon } from '@heroicons/react/24/outline';

/**
 * Accessible disclosure: a real <button> header wired to its region with
 * aria-expanded / aria-controls. The whole header row is the control, so the
 * hit area is the full width rather than a small chevron.
 */
export default function Disclosure({
  title,
  count,
  icon: Icon,
  defaultOpen = false,
  children,
  className = '',
  onOpen,
}) {
  const [open, setOpen] = useState(defaultOpen);
  const regionId = useId();
  const buttonId = useId();

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && onOpen) onOpen();
  };

  return (
    <section className={`rd-panel ${className}`}>
      <h2 style={{ margin: 0 }}>
        <button
          type="button"
          id={buttonId}
          className="rd-panel-head"
          aria-expanded={open}
          aria-controls={regionId}
          onClick={toggle}
        >
          {Icon ? <Icon aria-hidden="true" className="rd-panel-icon" /> : null}
          <span>{title}</span>
          {/* The count is shown as a bare badge but read as a phrase, so the
              accessible name is "Revision history, 2 items" rather than the
              run-together "Revision history2". */}
          {count != null ? (
            <span className="rd-panel-count">
              <span aria-hidden="true">{count}</span>
              <span className="rd-visually-hidden">
                {`, ${count} ${count === 1 ? 'item' : 'items'}`}
              </span>
            </span>
          ) : null}
          <ChevronDownIcon
            aria-hidden="true"
            className="rd-panel-chevron"
            style={count != null ? undefined : { marginLeft: 'auto' }}
          />
        </button>
      </h2>
      <div
        id={regionId}
        role="region"
        aria-labelledby={buttonId}
        hidden={!open}
        className="rd-panel-body"
      >
        {open ? children : null}
      </div>
    </section>
  );
}
