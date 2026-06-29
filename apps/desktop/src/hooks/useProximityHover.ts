import {
  useRef,
  useState,
  useCallback,
  useEffect,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from "react";

/**
 * Pointer-nearest-item tracker behind the "fluid" hover on FF-style row
 * controls (RadioGroup, CheckboxGroup, tabs). Ported from Fluid Functionalism
 * (registry/default/hooks/use-proximity-hover) — pure React, no deps. The
 * container reports the index of the item the pointer is over (or nearest to),
 * coalesced to one rAF per move; consumers drive an absolutely-positioned
 * indicator from `itemRects[activeIndex]`.
 */

export interface ItemRect {
  top: number;
  height: number;
  left: number;
  width: number;
}

interface UseProximityHoverOptions {
  axis?: "x" | "y";
}

interface UseProximityHoverReturn {
  activeIndex: number | null;
  setActiveIndex: Dispatch<SetStateAction<number | null>>;
  itemRects: ItemRect[];
  sessionRef: RefObject<number>;
  handlers: {
    onMouseMove: (e: React.MouseEvent) => void;
    onMouseEnter: () => void;
    onMouseLeave: () => void;
  };
  registerItem: (index: number, element: HTMLElement | null) => void;
  measureItems: () => void;
}

export function useProximityHover<T extends HTMLElement>(
  containerRef: RefObject<T | null>,
  options: UseProximityHoverOptions = {},
): UseProximityHoverReturn {
  const { axis = "y" } = options;
  const itemsRef = useRef(new Map<number, HTMLElement>());
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [itemRects, setItemRects] = useState<ItemRect[]>([]);
  const itemRectsRef = useRef<ItemRect[]>([]);
  const sessionRef = useRef(0);
  const rafIdRef = useRef<number | null>(null);
  const remeasureRafIdRef = useRef<number | null>(null);

  const measureItems = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const rects: ItemRect[] = [];
    itemsRef.current.forEach((element, index) => {
      // offset* (not getBoundingClientRect) so measurements are unaffected by
      // CSS transforms on an ancestor (e.g. a parent scaleY animation), and
      // match the coordinate space of `position: absolute` children.
      rects[index] = {
        top: element.offsetTop,
        height: element.offsetHeight,
        left: element.offsetLeft,
        width: element.offsetWidth,
      };
    });
    itemRectsRef.current = rects;
    setItemRects(rects);
  }, [containerRef]);

  const registerItem = useCallback(
    (index: number, element: HTMLElement | null) => {
      if (element) {
        itemsRef.current.set(index, element);
      } else {
        itemsRef.current.delete(index);
      }
      // Coalesce rapid register/unregister (e.g. AnimatePresence remounts) into
      // a single remeasure next frame, so consumers needn't call measureItems.
      if (remeasureRafIdRef.current !== null) {
        cancelAnimationFrame(remeasureRafIdRef.current);
      }
      remeasureRafIdRef.current = requestAnimationFrame(() => {
        remeasureRafIdRef.current = null;
        measureItems();
      });
    },
    [measureItems],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const mouseX = e.clientX;
      const mouseY = e.clientY;

      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
      }

      rafIdRef.current = requestAnimationFrame(() => {
        rafIdRef.current = null;
        const container = containerRef.current;
        if (!container) return;

        const containerRect = container.getBoundingClientRect();
        const mousePos = axis === "x" ? mouseX : mouseY;

        let closestIndex: number | null = null;
        let closestDistance = Infinity;
        let containingIndex: number | null = null;

        const rects = itemRectsRef.current;
        const scrollOffset = axis === "x" ? container.scrollLeft : container.scrollTop;
        const borderOffset = axis === "x" ? container.clientLeft : container.clientTop;
        const containerEdge = axis === "x" ? containerRect.left : containerRect.top;
        // Item rects are layout values (offset*); the container's bounding rect
        // reflects any ancestor `transform: scale`. Map layout coords into the
        // visual viewport space the cursor lives in.
        const layoutSize = axis === "x" ? container.offsetWidth : container.offsetHeight;
        const visualSize = axis === "x" ? containerRect.width : containerRect.height;
        const scale = layoutSize > 0 ? visualSize / layoutSize : 1;

        for (let index = 0; index < rects.length; index++) {
          const r = rects[index];
          if (!r) continue;

          const contentPos = axis === "x" ? r.left : r.top;
          const itemStart = containerEdge + (borderOffset + contentPos - scrollOffset) * scale;
          const itemSize = (axis === "x" ? r.width : r.height) * scale;
          const itemEnd = itemStart + itemSize;

          if (mousePos >= itemStart && mousePos <= itemEnd) {
            containingIndex = index;
          }

          const itemCenter = itemStart + itemSize / 2;
          const distance = Math.abs(mousePos - itemCenter);

          if (distance < closestDistance) {
            closestDistance = distance;
            closestIndex = index;
          }
        }

        setActiveIndex(containingIndex ?? closestIndex);
      });
    },
    [axis, containerRef],
  );

  const handleMouseEnter = useCallback(() => {
    sessionRef.current += 1;
  }, []);

  const handleMouseLeave = useCallback(() => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    setActiveIndex(null);
  }, []);

  useEffect(() => {
    return () => {
      if (rafIdRef.current !== null) cancelAnimationFrame(rafIdRef.current);
      if (remeasureRafIdRef.current !== null) cancelAnimationFrame(remeasureRafIdRef.current);
    };
  }, []);

  return {
    activeIndex,
    setActiveIndex,
    itemRects,
    sessionRef,
    handlers: {
      onMouseMove: handleMouseMove,
      onMouseEnter: handleMouseEnter,
      onMouseLeave: handleMouseLeave,
    },
    registerItem,
    measureItems,
  };
}

/** Child-item self-registration: call in an effect with the item ref + index. */
export function useRegisterProximityItem(
  registerItem: (index: number, element: HTMLElement | null) => void,
  index: number,
  ref: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    registerItem(index, ref.current);
    return () => registerItem(index, null);
  }, [index, registerItem, ref]);
}
