#!/usr/bin/env node
import { iniciarServidorEpe4md } from "./server.js";

iniciarServidorEpe4md().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
