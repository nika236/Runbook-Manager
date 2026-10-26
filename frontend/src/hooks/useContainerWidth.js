import { useCallback, useEffect, useState } from 'react';

/**
 * Observe the rendered width of an element.
 *
 * The reader's two-column breakpoint depends on the space actually available to
 * the article, not on the viewport: the app has a 240px left navigation, so a
 * 1280px viewport only offers ~976px of content. Measuring the container keeps
 * the article at a comfortable measure instead of squeezing it to fit a rail.
 *
 * @returns {[Function, number]} A ref callback to attach, and the current width.
 */
export default function useContainerWidth() {
  const [node, setNode] = useState(null);
  const [width, setWidth] = useState(0);

  const ref = useCallback((el) => setNode(el), []);

  useEffect(() => {
    if (!node) return undefined;

    if (typeof ResizeObserver === 'undefined') {
      setWidth(node.getBoundingClientRect().width);
      return undefined;
    }

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setWidth(entry.contentRect.width);
    });
    observer.observe(node);
    setWidth(node.getBoundingClientRect().width);
    return () => observer.disconnect();
  }, [node]);

  return [ref, width];
}
