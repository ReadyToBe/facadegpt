import { create } from "zustand";

export const useFacadeStore = create((set) => ({
  currentProject: null,
  projectInfo: null,
  parameterRanges: [],
  schemes: [],
  currentScheme: null,
  setProjectBundle: (bundle) => set({
    currentProject: bundle.project,
    projectInfo: bundle.project_info,
    parameterRanges: bundle.parameter_ranges || [],
  }),
  setParsed: (parsed) => set({
    projectInfo: parsed.project_info,
    parameterRanges: parsed.parameter_ranges,
  }),
  setSchemes: (schemes) => set({ schemes }),
  setCurrentScheme: (scheme) => set({ currentScheme: scheme }),
}));
