"use client";
import { useEffect, useRef } from "react";

interface Props {
  analyserNode: AnalyserNode | null;
  isActive: boolean;
}

export default function AudioWaveform({ analyserNode, isActive }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    function draw() {
      if (!canvas || !ctx) return;
      rafRef.current = requestAnimationFrame(draw);

      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);

      if (!analyserNode || !isActive) {
        ctx.beginPath();
        ctx.strokeStyle = "rgba(45,24,18,0.2)";
        ctx.lineWidth = 1.5;
        ctx.moveTo(0, height / 2);
        ctx.lineTo(width, height / 2);
        ctx.stroke();
        return;
      }

      const bufferLength = analyserNode.fftSize;
      const dataArray = new Uint8Array(bufferLength);
      analyserNode.getByteTimeDomainData(dataArray);

      ctx.beginPath();
      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 2;

      const sliceWidth = width / bufferLength;
      let x = 0;
      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * height) / 2;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        x += sliceWidth;
      }
      ctx.lineTo(width, height / 2);
      ctx.stroke();
    }

    draw();
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [analyserNode, isActive]);

  return (
    <canvas
      ref={canvasRef}
      width={280}
      height={44}
      className="w-full rounded-xl"
      style={{ background: "transparent" }}
    />
  );
}
