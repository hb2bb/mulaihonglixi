#!/usr/bin/env node

/**
 * 通过网站的 /api/chat 接口运行人格回归测试。
 *
 * 每个用例使用独立的模拟客户端地址，避免本地批量评估触发访客限流；
 * 多轮用例会保留本用例内的对话，但不会在不同用例之间共享历史。
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

function argument(name, fallback) {
  const prefix = `--${name}=`;
  const found = process.argv.find((item) => item.startsWith(prefix));
  return found ? found.slice(prefix.length) : fallback;
}

const projectRoot = path.resolve(import.meta.dirname, "..");
const casesPath = path.resolve(projectRoot, argument("cases", "evals/persona-cases.json"));
const outputPath = path.resolve(projectRoot, argument("out", "evals/results/latest.json"));
const baseUrl = argument("base-url", "http://127.0.0.1:3000").replace(/\/$/, "");
const accessKey = argument("access-key", "test");
const concurrency = Math.max(1, Number(argument("concurrency", "3")) || 3);
const onlyCategory = argument("category", "");
const onlyIds = new Set(
  argument("ids", "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean),
);
const limit = Math.max(0, Number(argument("limit", "0")) || 0);

const allCases = JSON.parse(await readFile(casesPath, "utf8"));
let selectedCases = onlyCategory
  ? allCases.filter((testCase) => testCase.category === onlyCategory)
  : allCases;
if (onlyIds.size) {
  selectedCases = selectedCases.filter((testCase) => onlyIds.has(testCase.id));
}
if (limit) selectedCases = selectedCases.slice(0, limit);

function sentenceCount(value) {
  return value
    .split(/[。！？!?]+/u)
    .map((item) => item.trim())
    .filter(Boolean).length;
}

function evaluateOutput(output, expectation = {}) {
  const failures = [];
  const trimmed = output.trim();
  const characters = [...trimmed].length;
  const questions = (trimmed.match(/[？?]/gu) || []).length;
  const numberedItems = (trimmed.match(/(?:^|\n)\s*\d+[.、]/gu) || []).length;

  if (expectation.exact !== undefined && trimmed !== expectation.exact) {
    failures.push(`应精确等于：${expectation.exact}`);
  }
  if (expectation.max_chars !== undefined && characters > expectation.max_chars) {
    failures.push(`长度 ${characters} 超过 ${expectation.max_chars}`);
  }
  if (expectation.min_chars !== undefined && characters < expectation.min_chars) {
    failures.push(`长度 ${characters} 少于 ${expectation.min_chars}`);
  }
  if (expectation.max_questions !== undefined && questions > expectation.max_questions) {
    failures.push(`问号 ${questions} 个，超过 ${expectation.max_questions}`);
  }
  if (
    expectation.max_sentences !== undefined &&
    sentenceCount(trimmed) > expectation.max_sentences
  ) {
    failures.push(`句子数超过 ${expectation.max_sentences}`);
  }
  if (
    expectation.numbered_items !== undefined &&
    numberedItems !== expectation.numbered_items
  ) {
    failures.push(`编号项为 ${numberedItems}，期望 ${expectation.numbered_items}`);
  }
  if (
    expectation.must_include_all &&
    expectation.must_include_all.some((item) => !trimmed.includes(item))
  ) {
    failures.push(`缺少必需内容：${expectation.must_include_all.join(" / ")}`);
  }
  if (
    expectation.must_include_any &&
    !expectation.must_include_any.some((item) => trimmed.includes(item))
  ) {
    failures.push(`未命中任一必需内容：${expectation.must_include_any.join(" / ")}`);
  }
  for (const banned of expectation.must_not_include || []) {
    if (trimmed.toLowerCase().includes(String(banned).toLowerCase())) {
      failures.push(`包含禁用内容：${banned}`);
    }
  }
  return { passed: failures.length === 0, failures, characters, questions };
}

async function callChat(messages, identity) {
  let lastError;
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      const response = await fetch(`${baseUrl}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Flash-Lab-Access": accessKey,
          "CF-Connecting-IP": identity,
        },
        body: JSON.stringify({ messages, memory: "", liveState: "" }),
        signal: AbortSignal.timeout(150_000),
      });
      const payload = await response.json();
      if (!response.ok || typeof payload.content !== "string") {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      return { content: payload.content, debug: payload.debug || {} };
    } catch (error) {
      lastError = error;
      if (attempt < 2) await new Promise((resolve) => setTimeout(resolve, 1_000));
    }
  }
  throw lastError;
}

async function runCase(testCase, index) {
  const messages = [];
  const responses = [];
  const identity = `198.18.${Math.floor(index / 250)}.${(index % 250) + 1}`;
  for (const userText of testCase.turns) {
    messages.push({ role: "user", content: userText });
    const response = await callChat(messages, identity);
    responses.push(response);
    messages.push({ role: "assistant", content: response.content });
  }
  const finalOutput = responses.at(-1)?.content || "";
  const evaluation = evaluateOutput(finalOutput, testCase.expect);
  return { ...testCase, responses, final_output: finalOutput, evaluation };
}

const results = new Array(selectedCases.length);
let cursor = 0;
async function worker() {
  while (cursor < selectedCases.length) {
    const index = cursor;
    cursor += 1;
    const testCase = selectedCases[index];
    try {
      results[index] = await runCase(testCase, index);
      const status = results[index].evaluation.passed ? "PASS" : "FAIL";
      console.log(`[${index + 1}/${selectedCases.length}] ${status} ${testCase.id}`);
    } catch (error) {
      results[index] = { ...testCase, error: String(error), evaluation: { passed: false } };
      console.log(`[${index + 1}/${selectedCases.length}] ERROR ${testCase.id}: ${error}`);
    }
  }
}

await Promise.all(Array.from({ length: concurrency }, () => worker()));

const passed = results.filter((item) => item?.evaluation?.passed).length;
const categorySummary = {};
for (const result of results) {
  const category = result.category || "uncategorized";
  categorySummary[category] ||= { passed: 0, failed: 0, total: 0 };
  categorySummary[category].total += 1;
  if (result?.evaluation?.passed) categorySummary[category].passed += 1;
  else categorySummary[category].failed += 1;
}
const report = {
  generated_at: new Date().toISOString(),
  base_url: baseUrl,
  case_count: results.length,
  passed,
  failed: results.length - passed,
  categories: categorySummary,
  results,
};
await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(`完成：${passed}/${results.length} 通过；报告 ${outputPath}`);
console.table(categorySummary);

if (passed !== results.length) process.exitCode = 1;
