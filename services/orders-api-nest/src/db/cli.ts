import "reflect-metadata"
import { createDataSource } from "./data-source.js"
import { seed } from "./seed.js"

const command = process.argv[2]
const ds = createDataSource(process.env.DATABASE_URL ?? "postgres://orders:orders@localhost:5436/orders")
await ds.initialize()
try {
  if (command === "migrate") {
    const done = await ds.runMigrations({ transaction: "each" })
    console.log(done.length ? `применено: ${done.map((m) => m.name).join(", ")}` : "новых миграций нет")
  } else if (command === "revert") {
    await ds.undoLastMigration()
    console.log("последняя миграция откачена")
  } else if (command === "seed") {
    console.log(await seed(ds, process.env.SEED_FILE, !process.argv.includes("--catalog-only")))
  } else {
    console.error("использование: cli.js migrate | revert | seed [--catalog-only]")
    process.exitCode = 2
  }
} finally {
  await ds.destroy()
}
