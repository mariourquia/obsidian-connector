import { t as RandomGenerator } from "../RandomGenerator-CKZRB3Fu.js";

//#region src/generator/mersenne.d.ts
declare function mersenneFromState(state: readonly number[]): RandomGenerator;
declare function mersenne(seed: number): RandomGenerator;
//#endregion
export { mersenne, mersenneFromState };