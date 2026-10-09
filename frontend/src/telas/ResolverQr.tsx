/**
 * O destino do QR code impresso no manifesto.
 *
 * A etiqueta carrega `/qr/<token>`, e não o id do manifesto: o token é um
 * identificador aleatório, que não revela quantos manifestos existem no
 * sistema. Esta tela troca o token pelo manifesto e segue para o detalhe dele.
 *
 * Quem aponta a câmera sem estar logado é desviado para o login e volta para
 * cá depois — o endereço pretendido é lembrado nas rotas (ver `App.tsx`).
 */

import { Navigate, useParams } from "react-router-dom";
import { api } from "../api/api";
import { AvisoDeErro, Carregando, TituloDaPagina } from "../componentes/Pagina";
import { useCarregamento } from "../useCarregamento";

export function ResolverQr() {
  const { token } = useParams();
  const { dado, carregando, erro } = useCarregamento(
    () => api.buscarManifestoPorToken(token ?? ""),
    token ?? "",
  );

  if (carregando) return <Carregando texto="Abrindo o manifesto da etiqueta…" />;

  // `replace` evita que o botão voltar caia de novo no token e repita a
  // consulta: para o usuário, a etiqueta levou direto ao manifesto.
  if (dado !== null) return <Navigate to={`/manifestos/${dado.id}`} replace />;

  return (
    <>
      <TituloDaPagina
        titulo="Etiqueta não reconhecida"
        legenda="O código lido não corresponde a nenhum manifesto que você possa ver."
      />
      {erro !== null && <AvisoDeErro erro={erro} />}
    </>
  );
}
