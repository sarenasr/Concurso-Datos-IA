import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DATIA — Habla con los datos de Colombia",
  description: "Asistente de IA para datos abiertos de Colombia (datos.gov.co)",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">
        {children}
      </body>
    </html>
  );
}
