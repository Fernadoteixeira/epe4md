import test from "node:test";
import assert from "node:assert/strict";
import { definicoesFerramentas } from "./server.js";
import { executarEpe4md, funcoesPublicasEpe4md } from "./index.js";

test("exposes every public R workflow as an MCP tool", () => {
  assert.deepEqual(definicoesFerramentas.map((definition) => definition.name), funcoesPublicasEpe4md);
  assert.equal(new Set(definicoesFerramentas.map((definition) => definition.name)).size, 22);
});

test("validates calculation arguments at the MCP boundary", () => {
  const definition = definicoesFerramentas.find((item) => item.name === "epe4md_calcula");

  assert.ok(definition);
  assert.equal(definition.schema.ano_base.safeParse(2021).success, true);
  assert.equal(definition.schema.ano_base.safeParse("2021").success, false);
  assert.equal(definition.schema.filtro_renda_domicilio.safeParse("maior_3sm").success, true);
  assert.equal(definition.schema.filtro_renda_domicilio.safeParse("invalid").success, false);
});

test("rejects non-public function names before spawning Python", async () => {
  await assert.rejects(
    executarEpe4md("not_public", {}),
    /functionName deve começar com epe4md_/,
  );
});
