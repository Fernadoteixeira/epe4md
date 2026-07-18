import test from "node:test";
import assert from "node:assert/strict";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { criarServidorEpe4md } from "./server.js";

test("executes a packaged premise workflow through MCP", async () => {
  const server = criarServidorEpe4md();
  const client = new Client({ name: "epe4md-e2e", version: "0.1.4" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();

  await server.connect(serverTransport);
  await client.connect(clientTransport);

  try {
    const response = await client.callTool({
      name: "epe4md_casos_payback",
      arguments: {
        arguments: {
          ano_base: 2021,
          ano_max_resultado: 2022,
        },
      },
    });

    assert.equal(response.isError, undefined);
    assert.ok(Array.isArray(response.content));
    assert.ok(response.content.length > 0);

    const [firstContent] = response.content;
    assert.equal(firstContent.type, "text");
    assert.ok(JSON.parse(firstContent.text).length > 0);
  } finally {
    await client.close();
    await server.close();
  }
});
