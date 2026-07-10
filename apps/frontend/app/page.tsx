import { Chat } from "@/components/chat";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 py-8">
      <header className="flex items-center gap-3">
        <span className="inline-block h-4 w-4 rounded-full bg-accent" aria-hidden />
        <h1 className="text-xl font-semibold tracking-tight">DATIA</h1>
        <span className="text-sm text-muted-foreground">
          Habla con los datos de Colombia
        </span>
      </header>
      <Chat />
    </main>
  );
}
