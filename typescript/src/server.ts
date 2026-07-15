import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { executarEpe4md, funcoesPublicasEpe4md, type FuncaoPublicaEpe4md, type Registro } from "./index.js";

const recordsSchema = z.array(z.record(z.unknown())).describe("Lista de linhas tabulares, cada uma como objeto JSON.");
const directorySchema = z.string().min(1).optional().describe("Diretório opcional com planilhas de premissas.");
const calculationArgumentsSchema = z.object({
  premissas_reg: recordsSchema,
  ano_base: z.number().int(),
  sequencial: z.boolean().optional(), filtro_de_uf: z.string().optional(), filtro_nome4md: z.string().optional(),
  filtro_de_segmento: z.string().optional(), filtro_de_custo_unitario_max: z.number().nullable().optional(),
  ano_max_resultado: z.number().int().max(2050).optional(), altera_sistemas_existentes: z.boolean().optional(),
  ano_decisao_alteracao: z.number().int().optional(), inflacao: z.number().optional(), taxa_desconto_nominal: z.number().optional(),
  custo_reforco_rede: z.number().optional(), ano_troca_inversor: z.number().int().optional(), pagamento_disponibilidade: z.number().optional(),
  disponibilidade_kwh_mes: z.number().optional(), filtro_renda_domicilio: z.enum(["total", "maior_1sm", "maior_2sm", "maior_3sm", "maior_5sm"]).optional(),
  desconto_capex_local: z.number().optional(), anos_desconto: z.union([z.number().int(), z.array(z.number().int())]).optional(),
  tx_cresc_grupo_a: z.number().optional(), spb: z.number().optional(), p_max: z.number().positive().optional(), q_max: z.number().positive().optional(),
  filtro_comercial: z.number().nullable().optional(), ajuste_ano_corrente: z.boolean().optional(), ultimo_mes_ajuste: z.number().int().min(1).max(12).optional(),
  metodo_ajuste: z.enum(["extrapola", "substitui"]).optional(), dir_dados_premissas: directorySchema,
});
const genericArgumentsSchema = z.object({ arguments: z.record(z.unknown()).default({}).describe("Argumentos da função pública epe4md, com os nomes portugueses originais.") });

type Definition = { name: FuncaoPublicaEpe4md; description: string; schema: Record<string, z.ZodTypeAny> };
export const definicoesFerramentas: Definition[] = funcoesPublicasEpe4md.map((name) => ({
  name,
  description: `Executa o cálculo somente-leitura ${name} do modelo EPE 4MD. Mantém a terminologia de Micro e Minigeração Distribuída.`,
  schema: name === "epe4md_calcula" ? calculationArgumentsSchema.shape : genericArgumentsSchema.shape,
}));

function removeUndefined(values: Record<string, unknown>): Registro {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined)) as Registro;
}

export function criarServidorEpe4md(): McpServer {
  const server = new McpServer({ name: "epe4md", version: "0.1.4" });
  for (const definition of definicoesFerramentas) {
    server.registerTool(definition.name, {
      title: definition.name,
      description: definition.description,
      inputSchema: definition.schema,
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    }, async (parameters) => {
      const argumentsObject = definition.name === "epe4md_calcula"
        ? removeUndefined(parameters as Record<string, unknown>)
        : (parameters as { arguments: Registro }).arguments;
      const result = await executarEpe4md(definition.name, argumentsObject);
      return { content: [{ type: "text", text: JSON.stringify(result) }] };
    });
  }
  return server;
}

export async function iniciarServidorEpe4md(): Promise<void> {
  const server = criarServidorEpe4md();
  await server.connect(new StdioServerTransport());
}
