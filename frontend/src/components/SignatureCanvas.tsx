import { useRef, useState, useEffect, useCallback } from 'react';

interface SignatureCanvasProps {
  onSignatureChange: (dataUrl: string | null) => void;
  width?: number;
  height?: number;
}

export default function SignatureCanvas({
  onSignatureChange,
  width = 400,
  height = 200,
}: SignatureCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [hasSignature, setHasSignature] = useState(false);

  // Initialize canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = '#1a1a2e';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
  }, [width, height]);

  const getCoords = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement> | React.TouchEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return { x: 0, y: 0 };
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;

      if ('touches' in e && e.touches.length > 0) {
        return {
          x: (e.touches[0].clientX - rect.left) * scaleX,
          y: (e.touches[0].clientY - rect.top) * scaleY,
        };
      }
      if ('nativeEvent' in e && 'offsetX' in (e as React.MouseEvent).nativeEvent) {
        const me = e as React.MouseEvent<HTMLCanvasElement>;
        return {
          x: me.nativeEvent.offsetX * scaleX,
          y: me.nativeEvent.offsetY * scaleY,
        };
      }
      return { x: 0, y: 0 };
    },
    []
  );

  const startDrawing = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement> | React.TouchEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const { x, y } = getCoords(e);
      ctx.beginPath();
      ctx.moveTo(x, y);
      setIsDrawing(true);
    },
    [getCoords]
  );

  const draw = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement> | React.TouchEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      if (!isDrawing) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const { x, y } = getCoords(e);
      ctx.lineTo(x, y);
      ctx.stroke();
    },
    [isDrawing, getCoords]
  );

  const stopDrawing = useCallback(() => {
    if (!isDrawing) return;
    setIsDrawing(false);
    setHasSignature(true);

    const canvas = canvasRef.current;
    if (canvas) {
      const dataUrl = canvas.toDataURL('image/png');
      onSignatureChange(dataUrl);
    }
  }, [isDrawing, onSignatureChange]);

  const clear = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = '#1a1a2e';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    setHasSignature(false);
    onSignatureChange(null);
  }, [width, height, onSignatureChange]);

  return (
    <div className="flex flex-col gap-2">
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        onMouseDown={startDrawing}
        onMouseMove={draw}
        onMouseUp={stopDrawing}
        onMouseLeave={stopDrawing}
        onTouchStart={startDrawing}
        onTouchMove={draw}
        onTouchEnd={stopDrawing}
        className="border-2 border-dashed border-gray-300 rounded-lg bg-white cursor-crosshair touch-none w-full"
        style={{ maxWidth: width }}
      />
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={clear}
          className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
        >
          Очистить
        </button>
        {hasSignature && (
          <span className="text-xs text-green-600">Подпись нарисована</span>
        )}
      </div>
    </div>
  );
}
