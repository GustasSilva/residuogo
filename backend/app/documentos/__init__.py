"""Geracao dos arquivos que o usuario baixa: PDF, CSV e imagem do QR code.

Separado dos servicos de proposito. Em `services/` esta a regra de negocio -
o que vale, quem pode, quanto deu. Aqui esta apenas a **apresentacao** desses
dados em um formato de arquivo. A consequencia pratica e que trocar o layout
do PDF nao toca em nenhuma regra, e corrigir uma regra nao mexe no layout.

Modulos:

* `qr.py`      - imagem do QR code e o endereco que ele carrega;
* `estilo.py`  - o que os dois PDFs tem em comum (pagina, cores, tabelas);
* `pdf_manifesto.py` - o manifesto em PDF, com QR code;
* `pdf_resumo.py`    - o resumo do periodo em PDF;
* `planilha.py`      - a listagem de manifestos em CSV.
"""
