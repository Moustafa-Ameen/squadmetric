interface FixtureChipProps {
  difficulty?: number;
  label?: string | number;
  opponentShortName?: string;
}

export function FixtureChip({ difficulty, label, opponentShortName }: FixtureChipProps) {
  const level = difficulty ?? 3;
  const tone = fixtureTone(level);
  const content = opponentShortName ? (
    <>
      <span className="leading-none">{opponentShortName}</span>
      <span className="font-mono text-[10px] leading-none opacity-85">{label ?? level}</span>
    </>
  ) : (
    label ?? level
  );

  return (
    <span
      className={`inline-flex min-h-7 min-w-[44px] flex-col items-center justify-center rounded-md px-1.5 text-[10px] font-black uppercase shadow-[inset_0_0_0_1px_rgba(255,255,255,0.12)] ${tone}`}
      title={opponentShortName ? `${opponentShortName} · FDR ${level}` : `FDR ${level}`}
    >
      {content}
    </span>
  );
}

function fixtureTone(level: number): string {
  if (level <= 2) return "bg-fpl-green text-white";
  if (level === 3) return "bg-fpl-amber text-black";
  if (level === 4) return "bg-fpl-red text-white";
  return "bg-[#7f1d1d] text-white";
}
