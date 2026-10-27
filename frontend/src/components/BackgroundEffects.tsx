export default function BackgroundEffects() {
  return (
    <>
      {/* Single subtle gradient background */}
      <div className="fixed inset-0 pointer-events-none" style={{ zIndex: -2 }}>
        <div className="absolute inset-0 bg-gradient-to-br from-dark-950 via-dark-900 to-dark-950" />
        <div className="absolute inset-0 opacity-30 bg-[radial-gradient(ellipse_at_top_left,rgba(6,182,212,0.08),transparent_50%)]" />
      </div>
    </>
  );
}
