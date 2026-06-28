export type UiContract = {
  key: string;
  version: string;
  schemaId: string;
  owner: string;
};

export const uiContracts: UiContract[] = [
  {
    key: "demo.result_card",
    version: "v1",
    schemaId: "demo.result_card.v1",
    owner: "demo-business-agent",
  },
];
