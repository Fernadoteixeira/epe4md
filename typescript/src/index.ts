import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { delimiter, dirname, resolve } from "node:path";

export type Registro = Record<string, unknown>;
export type Registros = Registro[];
export type ResultadoEpe4md = Registros | Record<string, Registros> | Record<string, unknown>;

const directory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(directory, "..", "..");
const pythonSourceDirectory = resolve(repositoryRoot, "python", "src");

/** Calls the canonical Python implementation through its stable JSON command interface. */
export async function executarEpe4md(functionName: string, argumentsObject: Registro): Promise<ResultadoEpe4md> {
  if (!functionName.startsWith("epe4md_")) {
    throw new Error("functionName deve começar com epe4md_.");
  }
  const executable = process.env.EPE4MD_PYTHON_EXECUTABLE ?? "python";
  const inheritedPath = process.env.PYTHONPATH;
  const environment = {
    ...process.env,
    PYTHONPATH: inheritedPath ? `${pythonSourceDirectory}${delimiter}${inheritedPath}` : pythonSourceDirectory,
  };
  const child = spawn(executable, ["-m", "epe4md.cli"], { cwd: repositoryRoot, env: environment, stdio: ["pipe", "pipe", "pipe"] });
  const standardOutput: Buffer[] = [];
  const standardError: Buffer[] = [];
  child.stdout.on("data", (data: Buffer) => standardOutput.push(data));
  child.stderr.on("data", (data: Buffer) => standardError.push(data));
  child.stdin.end(JSON.stringify({ function: functionName, arguments: argumentsObject }));
  const code = await new Promise<number | null>((complete, fail) => {
    child.once("error", fail);
    child.once("close", complete);
  });
  const errorText = Buffer.concat(standardError).toString("utf8").trim();
  if (code !== 0) {
    throw new Error(`A execução Python de ${functionName} falhou${errorText ? `: ${errorText}` : "."}`);
  }
  const text = Buffer.concat(standardOutput).toString("utf8");
  try {
    return JSON.parse(text) as ResultadoEpe4md;
  } catch (error) {
    throw new Error(`A execução Python de ${functionName} retornou JSON inválido: ${error instanceof Error ? error.message : String(error)}.`);
  }
}

export const funcoesPublicasEpe4md = [
  "epe4md_calcula", "epe4md_calibra_curva_s", "epe4md_casos_payback", "epe4md_fatores_publicacao",
  "epe4md_graf_geracao_ano", "epe4md_graf_geracao_mes", "epe4md_graf_part_fonte_geracao",
  "epe4md_graf_part_fonte_potencia", "epe4md_graf_part_segmento", "epe4md_graf_pot_acum",
  "epe4md_graf_pot_anual", "epe4md_graf_pot_regiao", "epe4md_graf_pot_segmento", "epe4md_investimentos",
  "epe4md_mercado_potencial", "epe4md_payback", "epe4md_prepara_base", "epe4md_proj_adotantes",
  "epe4md_proj_geracao", "epe4md_proj_mensal", "epe4md_proj_potencia", "epe4md_sumariza_resultados",
] as const;
export type FuncaoPublicaEpe4md = (typeof funcoesPublicasEpe4md)[number];
