import { useState, useEffect } from 'react';
import { getSpaces } from '../api/client';

let _cache = null;
let _promise = null;

/** Force the next resolveSpace() consumer to refetch space names from the backend. */
export function invalidateSpaceNamesCache() {
  _cache = null;
  _promise = null;
}

function fetchOnce() {
  if (!_promise) {
    _promise = getSpaces()
      .then((data) => {
        const map = {};
        (data.spaces || data || []).forEach((s) => {
          if (s.key && s.name && s.name !== s.key) map[s.key] = s.name;
        });
        _cache = map;
        return map;
      })
      .catch(() => {
        _cache = {};
        return {};
      });
  }
  return _promise;
}

export default function useSpaceNames() {
  const [names, setNames] = useState(_cache || {});

  useEffect(() => {
    if (_cache) {
      setNames(_cache);
      return;
    }
    fetchOnce().then(setNames);
  }, []);

  const resolve = (key) => names[key] || key;

  return { spaceNames: names, resolveSpace: resolve };
}
