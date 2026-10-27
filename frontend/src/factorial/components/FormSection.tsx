import { ReactNode } from 'react';

export default function FormSection({
  heading,
  children,
}: {
  heading?: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      {heading && <h2 className="text-fx-base font-semibold">{heading}</h2>}
      <div className="space-y-3">{children}</div>
    </section>
  );
}
