import type { Metadata } from "next";
import { Geologica } from "next/font/google";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

const geologica = Geologica({
  subsets: ["latin"],
  variable: "--font-geologica",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Manglar — Habla con los datos de Colombia",
  description:
    "Manglar es el asistente de IA para los datos abiertos de Colombia (datos.gov.co)",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`h-full antialiased ${geologica.variable} ${GeistMono.variable}`}
    >
      <body className="min-h-full flex flex-col font-sans">{children}</body>
    </html>
  );
}
