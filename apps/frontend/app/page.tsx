import { Chat } from "@/components/chat";
import { BarChart3 } from "lucide-react";

export default function Home() {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <header className="flex shrink-0 items-center gap-3 border-b bg-background px-4 py-3 md:px-6">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent shadow-sm">
          <BarChart3 className="h-5 w-5 text-accent-foreground" />
        </div>
        <div className="flex flex-col">
          <h1 className="text-lg font-bold tracking-tight leading-tight">
            DATIA
          </h1>
          <p className="text-xs text-muted-foreground leading-tight">
            Habla con los datos de Colombia
          </p>
        </div>
        <div className="ml-auto hidden items-center gap-1.5 sm:flex">
          <span className="h-2.5 w-2.5 rounded-full bg-colombia-yellow" />
          <span className="h-2.5 w-2.5 rounded-full bg-colombia-blue" />
          <span className="h-2.5 w-2.5 rounded-full bg-colombia-red" />
        </div>
      </header>
      <Chat />
    </div>
  );
}
