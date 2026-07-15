import test from "node:test";
import assert from "node:assert/strict";
import { definicoesFerramentas } from "./server.js";
import { funcoesPublicasEpe4md } from "./index.js";

test("exposes every public R workflow as an MCP tool", () => {
  assert.deepEqual(definicoesFerramentas.map((definition) => definition.name), funcoesPublicasEpe4md);
  assert.equal(new Set(definicoesFerramentas.map((definition) => definition.name)).size, 22);
});
