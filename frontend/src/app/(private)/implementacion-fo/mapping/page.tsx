import { Metadata } from "next";
import MappingPrediosView from "@/modules/implementacion-fo/mapping/MappingPrediosView";

export const metadata: Metadata = {
  title: "Mapping de Predios - Implementación FO - CINCO SAS",
  description: "Módulo de levantamiento predial y cartográfico de Implementación FO - CINCO SAS.",
};

const MappingPrediosPage = () => {
  return <MappingPrediosView />;
};

export default MappingPrediosPage;
