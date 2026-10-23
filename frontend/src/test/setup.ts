import "@testing-library/jest-dom/vitest";

// API navigateur absentes de jsdom, utilisées par Radix (positionnement, pointeur), cmdk et sonner.
if (typeof window !== "undefined") {
  if (!("ResizeObserver" in window)) {
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    Object.defineProperty(window, "ResizeObserver", { value: ResizeObserverStub, writable: true });
    Object.defineProperty(globalThis, "ResizeObserver", { value: ResizeObserverStub, writable: true });
  }
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener() {},
        removeListener() {},
        addEventListener() {},
        removeEventListener() {},
        dispatchEvent: () => false,
      }),
    });
  }
  const proto = window.HTMLElement.prototype as HTMLElement & Record<string, unknown>;
  if (!proto.scrollIntoView) proto.scrollIntoView = function scrollIntoView() {};
  if (!proto.hasPointerCapture) proto.hasPointerCapture = () => false;
  if (!proto.setPointerCapture) proto.setPointerCapture = () => {};
  if (!proto.releasePointerCapture) proto.releasePointerCapture = () => {};
}
