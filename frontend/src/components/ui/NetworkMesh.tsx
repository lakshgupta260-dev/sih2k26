import { useEffect, useRef } from "react";

/**
 * An interactive constellation that reacts to the cursor: nodes drift, ease
 * away from the pointer, and link up when they get close.
 *
 * Deliberately confined to the dark marketing panel on the auth screens. The
 * same effect behind a data table would fight the numbers for attention, and
 * this product is read by planners, not admired.
 *
 * It is decoration, so it yields: `prefers-reduced-motion` and a hidden tab
 * both stop the loop rather than burning a core on frames nobody sees.
 */
export function NetworkMesh({
  nodeColor = "#86868b",
  accentColor = "#8a3446",
  linkColor = "93, 176, 252",
  className = "",
}: {
  nodeColor?: string;
  accentColor?: string;
  linkColor?: string;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    const parent = canvas.parentElement;
    let width = 0;
    let height = 0;
    let frame = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    const pointer = { x: -9999, y: -9999, sx: -9999, sy: -9999 };

    const resize = () => {
      const rect = (parent ?? canvas).getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const observer = new ResizeObserver(resize);
    if (parent) observer.observe(parent);

    const onMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = e.clientX - rect.left;
      pointer.y = e.clientY - rect.top;
    };
    const onLeave = () => {
      pointer.x = -9999;
      pointer.y = -9999;
    };
    window.addEventListener("mousemove", onMove);
    document.addEventListener("mouseleave", onLeave);

    interface Node {
      x: number;
      y: number;
      vx: number;
      vy: number;
      r: number;
      accent: boolean;
    }

    const count = Math.max(28, Math.min(70, Math.floor((width * height) / 18000)));
    const nodes: Node[] = Array.from({ length: count }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.32,
      vy: (Math.random() - 0.5) * 0.32,
      r: Math.random() * 1.6 + 0.9,
      accent: Math.random() > 0.75,
    }));

    const LINK_DIST = 118;
    const PUSH_DIST = 150;

    const draw = () => {
      ctx.clearRect(0, 0, width, height);

      // Trail the cursor rather than snapping to it — the glow reads as
      // something with weight instead of a jittery dot.
      pointer.sx += (pointer.x - pointer.sx) * 0.08;
      pointer.sy += (pointer.y - pointer.sy) * 0.08;

      if (pointer.x > -1000) {
        const glow = ctx.createRadialGradient(pointer.sx, pointer.sy, 8, pointer.sx, pointer.sy, 170);
        glow.addColorStop(0, `rgba(${linkColor}, 0.10)`);
        glow.addColorStop(1, `rgba(${linkColor}, 0)`);
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(pointer.sx, pointer.sy, 170, 0, Math.PI * 2);
        ctx.fill();
      }

      for (const n of nodes) {
        n.x += n.vx;
        n.y += n.vy;

        const dx = pointer.x - n.x;
        const dy = pointer.y - n.y;
        const dist = Math.hypot(dx, dy);
        if (dist < PUSH_DIST && dist > 0.5) {
          const force = (PUSH_DIST - dist) / PUSH_DIST;
          n.x -= (dx / dist) * force * 1.1;
          n.y -= (dy / dist) * force * 1.1;
        }

        if (n.x < 0 || n.x > width) n.vx *= -1;
        if (n.y < 0 || n.y > height) n.vy *= -1;
        n.x = Math.max(0, Math.min(width, n.x));
        n.y = Math.max(0, Math.min(height, n.y));

        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = n.accent ? accentColor : nodeColor;
        ctx.globalAlpha = n.accent ? 0.75 : 0.5;
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      ctx.lineWidth = 0.6;
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const d = Math.hypot(dx, dy);
          if (d < LINK_DIST) {
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(${linkColor}, ${((LINK_DIST - d) / LINK_DIST) * 0.22})`;
            ctx.stroke();
          }
        }
      }

      frame = requestAnimationFrame(draw);
    };

    const start = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(draw);
    };
    const onVisibility = () => (document.hidden ? cancelAnimationFrame(frame) : start());
    document.addEventListener("visibilitychange", onVisibility);
    start();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseleave", onLeave);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [nodeColor, accentColor, linkColor]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className={`pointer-events-none absolute inset-0 select-none ${className}`}
    />
  );
}

/**
 * Perspective tilt with a specular highlight tracking the cursor. Kept subtle
 * (6°, not 12°) because these cards carry project data — it should feel
 * responsive, not like a toy.
 */
export function TiltCard({
  children,
  className = "",
  max = 6,
}: {
  children: React.ReactNode;
  className?: string;
  max?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    const rect = el.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const ry = ((px - rect.width / 2) / (rect.width / 2)) * max;
    const rx = -((py - rect.height / 2) / (rect.height / 2)) * max;

    // Written straight to style: routing per-frame pointer values through
    // React state re-renders the subtree on every mousemove.
    el.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg) scale(1.015)`;
  };

  const reset = () => {
    const el = ref.current;
    if (el) el.style.transform = "perspective(900px) rotateX(0deg) rotateY(0deg) scale(1)";
  };

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={reset}
      className={`relative transition-transform duration-300 ease-out will-change-transform ${className}`}
    >
      {children}
    </div>
  );
}
