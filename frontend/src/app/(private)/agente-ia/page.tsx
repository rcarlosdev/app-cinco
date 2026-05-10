import { Metadata } from "next";
import AgenteIAModule from "@/modules/agente-ia/AgenteIAModule";

export const metadata: Metadata = {
  title: "Agente IA - CINCO SAS",
  description: "Chat conversacional con dashboard analitico split-view.",
};

const AgenteIAPage = () => {
  return <AgenteIAModule />;
};

export default AgenteIAPage;
