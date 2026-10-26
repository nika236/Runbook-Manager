import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ChevronRightIcon, ChevronDownIcon, DocumentTextIcon } from '@heroicons/react/24/outline';

const slugify = (text) =>
  (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

function TreeNode({ node, spaceKey, depth = 0, activePageId }) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;
  const isActive = node.id === activePageId;

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 py-1 rounded-md transition-colors ${
          isActive ? 'bg-brand-50 text-brand-700' : 'hover:bg-slate-50'
        }`}
        style={{ paddingLeft: `${depth * 16 + 8}px`, paddingRight: '8px' }}
      >
        {hasChildren ? (
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-0.5 rounded hover:bg-slate-200 transition-colors"
          >
            {expanded
              ? <ChevronDownIcon className="h-3 w-3 text-slate-400" />
              : <ChevronRightIcon className="h-3 w-3 text-slate-400" />
            }
          </button>
        ) : (
          <span className="w-4" />
        )}
        <DocumentTextIcon className={`h-3.5 w-3.5 flex-shrink-0 ${isActive ? 'text-brand-500' : 'text-slate-400'}`} />
        <Link
          to={`/spaces/${spaceKey}/pages/${node.id}/${slugify(node.title)}`}
          className={`text-[13px] truncate ${
            isActive ? 'font-medium text-brand-700' : 'text-slate-600 hover:text-slate-900'
          }`}
          title={node.title}
        >
          {node.title}
        </Link>
      </div>
      {expanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNode key={child.id} node={child} spaceKey={spaceKey} depth={depth + 1} activePageId={activePageId} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function PageTree({ tree = [], spaceKey }) {
  const { pageId } = useParams();

  if (!tree.length) {
    return (
      <div className="px-3 py-4 text-center">
        <div className="text-sm text-slate-400">No pages in this space</div>
        <div className="text-2xs text-slate-300 mt-1">Run a sync to import content</div>
      </div>
    );
  }

  return (
    <div>
      {tree.map((node) => (
        <TreeNode key={node.id} node={node} spaceKey={spaceKey} activePageId={pageId} />
      ))}
    </div>
  );
}
