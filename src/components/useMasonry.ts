import { useLayoutEffect, useRef, type RefObject } from 'react';
import { feedColumnCount } from '../feedLayout';

export default function useMasonry(container: RefObject<HTMLDivElement | null>, enabled: boolean, itemsKey: string, layoutKey: string) {
  const placement = useRef({ key: '', count: 0, lanes: new Map<string, number>() });
  useLayoutEffect(() => {
    const columns = container.current?.querySelector<HTMLElement>('.workflow-columns');
    if (!columns || !enabled) return;
    const items = Array.from(columns.children) as HTMLElement[];
    const measure = () => {
      const count = feedColumnCount(columns.clientWidth);
      if (placement.current.key !== layoutKey || placement.current.count !== count) {
        placement.current = { key: layoutKey, count, lanes: new Map() };
      }
      const ends = Array<number>(count).fill(0);
      const heights = items.map(item => Math.ceil(item.getBoundingClientRect().height));
      // Keep existing lane assignments when content height or SQLite row order changes.
      const lanes = placement.current.lanes;
      for (const [index, item] of items.entries()) {
        const lane = lanes.get(item.dataset.module!);
        if (lane !== undefined) ends[lane] += heights[index] + 12;
      }
      for (const [index, item] of items.entries()) {
        const name = item.dataset.module!;
        if (!lanes.has(name)) {
          const lane = name === '' ? 0 : ends.indexOf(Math.min(...ends));
          lanes.set(name, lane);
          ends[lane] += heights[index] + 12;
        }
      }
      ends.fill(0);
      for (const [index, item] of items.entries()) {
        const lane = lanes.get(item.dataset.module!)!;
        item.style.gridColumn = String(lane + 1);
        item.style.gridRowStart = String(ends[lane] + 1);
        item.style.gridRowEnd = `span ${heights[index]}`;
        ends[lane] += heights[index] + 12;
      }
    };
    const observer = new ResizeObserver(measure);
    observer.observe(columns);
    items.forEach(item => observer.observe(item));
    measure();
    return () => {
      observer.disconnect();
      items.forEach(item => ['grid-row-end', 'grid-row-start', 'grid-column'].forEach(property => item.style.removeProperty(property)));
    };
  }, [container, enabled, itemsKey, layoutKey]);
}
