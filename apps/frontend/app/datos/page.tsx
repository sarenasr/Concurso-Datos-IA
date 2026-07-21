"use client";

import { ManglarBubble } from "@/components/manglar-bubble";
import { Search } from "lucide-react";

const SECTORS = [
  { emoji: "🏥", name: "Salud" },
  { emoji: "🎓", name: "Educación" },
  { emoji: "📋", name: "Contratación" },
  { emoji: "🌿", name: "Ambiente" },
  { emoji: "💰", name: "Economía" },
  { emoji: "🤝", name: "Inclusión Social" },
];

const DATASETS = [
  {
    name: "Contratos del Estado Colombiano 2024",
    desc: "Registro completo de contratos adjudicados por entidades públicas durante 2024.",
    views: "12.4k",
  },
  {
    name: "Cobertura de Vacunación Nacional",
    desc: "Datos de cobertura de vacunación por departamento y grupo etario.",
    views: "9.8k",
  },
  {
    name: "Matrículas en Educación Superior",
    desc: "Estudiantes matriculados en instituciones de educación superior por programa.",
    views: "8.2k",
  },
  {
    name: "Índice de Calidad del Aire",
    desc: "Mediciones diarias de calidad del aire en principales ciudades del país.",
    views: "7.1k",
  },
];

export default function DatosPage() {
  return (
    <div className="min-h-screen flex flex-col bg-white text-gray-900">
      <header className="shrink-0 bg-[#003893]">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <span className="text-lg font-bold tracking-tight text-white whitespace-nowrap">
            datos.gov.co
          </span>
          <div className="relative ml-auto hidden max-w-xs flex-1 sm:block">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/50" />
            <input
              type="text"
              placeholder="Buscar en datos.gov.co"
              className="w-full rounded-md border border-white/20 bg-white/10 py-1.5 pl-9 pr-3 text-sm text-white placeholder:text-white/50 focus:border-white/40 focus:outline-none"
              readOnly
            />
          </div>
        </div>
      </header>

      <section className="bg-gradient-to-b from-[#003893] to-[#00254d] px-4 py-16 text-center text-white sm:py-20">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
          Datos Abiertos de Colombia
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-base text-white/80 sm:text-lg">
          Encuentra, explora y usa datos del Estado Colombiano
        </p>
        <div className="mx-auto mt-8 flex max-w-xl items-center overflow-hidden rounded-xl bg-white shadow-lg">
          <Search className="ml-4 h-5 w-5 shrink-0 text-gray-400" />
          <input
            type="text"
            placeholder="Buscar datasets..."
            className="w-full px-3 py-4 text-base text-gray-900 placeholder:text-gray-400 focus:outline-none"
            readOnly
          />
        </div>
      </section>

      <section className="mx-auto w-full max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <h2 className="mb-6 text-xl font-bold text-gray-900">
          Explora por sector
        </h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {SECTORS.map((s) => (
            <div
              key={s.name}
              className="flex flex-col items-center rounded-xl border border-gray-200 bg-white p-5 text-center shadow-sm transition-shadow hover:shadow-md"
            >
              <span className="mb-3 text-4xl" role="img" aria-label={s.name}>
                {s.emoji}
              </span>
              <span className="mb-2 text-sm font-semibold text-gray-900">
                {s.name}
              </span>
              <span className="text-xs font-medium text-[#003893]">
                Ver datasets →
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto w-full max-w-7xl px-4 pb-16 sm:px-6 lg:px-8">
        <h2 className="mb-6 text-xl font-bold text-gray-900">
          Datasets más vistos
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {DATASETS.map((d) => (
            <div
              key={d.name}
              className="flex flex-col rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md"
            >
              <h3 className="mb-2 text-sm font-bold leading-snug text-[#003893]">
                {d.name}
              </h3>
              <p className="mb-4 flex-1 text-xs leading-relaxed text-gray-600">
                {d.desc}
              </p>
              <div className="flex items-center gap-1 text-xs text-gray-400">
                <Search className="h-3 w-3" />
                <span>{d.views} visualizaciones</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <footer className="mt-auto border-t border-gray-200 bg-gray-50 px-4 py-6 text-center text-sm text-gray-500">
        Ministerio TIC · Gobierno de Colombia
      </footer>

      <ManglarBubble />
    </div>
  );
}
