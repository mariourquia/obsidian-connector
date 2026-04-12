import chalk from "chalk";

/** Write a diagnostic/status message to stderr (never pollutes stdout/JSON). */
export function stderr(message: string): void {
  process.stderr.write(message + "\n");
}

/** Write a styled diagnostic to stderr. */
export function stderrDim(message: string): void {
  process.stderr.write(chalk.dim(message) + "\n");
}
