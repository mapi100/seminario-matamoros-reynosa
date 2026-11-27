(function () {
    "use strict";

    const declaration = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
    const sheetNamespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
    const documentRelationships = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    const mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    const writer = new TextEncoder();

    function escapeXml(value) {
        return String(value).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/g, "")
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&apos;");
    }

    function columnName(index) {
        let name = "";
        for (let n = index + 1; n > 0; n = Math.floor((n - 1) / 26)) {
            name = String.fromCharCode(65 + (n - 1) % 26) + name;
        }
        return name;
    }

    function relationships(items) {
        return '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
            items.map(([type, target], index) => '<Relationship Id="rId' + (index + 1) + '" Type="' +
                documentRelationships + '/' + type + '" Target="' + target + '"/>').join("") +
            '</Relationships>';
    }

    function worksheet(sheet) {
        const frozen = sheet.freezeColumns ?
            '<sheetViews><sheetView workbookViewId="0"><pane xSplit="' + sheet.freezeColumns +
            '" ySplit="' + sheet.headingRow + '" topLeftCell="' + columnName(sheet.freezeColumns) +
            (sheet.headingRow + 1) + '" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>' : "";
        const columns = '<cols>' + sheet.widths.map((width, i) =>
            '<col min="' + (i + 1) + '" max="' + (i + 1) + '" width="' + width + '" customWidth="1"/>').join("") + '</cols>';
        const rows = sheet.rows.map((row, index) => {
            const number = index + 1;
            const heading = number === 1 || number === sheet.headingRow;
            const cells = row.map((cell, i) => {
                if (cell === null || cell === undefined) return "";
                const ref = columnName(i) + number;
                const decimal = typeof cell === "object";
                const value = decimal ? cell.decimal : cell;
                if (typeof value === "number" && Number.isFinite(value)) {
                    const style = decimal ? (cell.failed ? 3 : 2) : 0;
                    return '<c r="' + ref + '" s="' + style + '"><v>' + value + '</v></c>';
                }
                // Texto literal incluso cuando un nombre empieza con =, +, - o @.
                return '<c r="' + ref + '" s="' + (heading ? 1 : 0) +
                    '" t="inlineStr"><is><t xml:space="preserve">' + escapeXml(value) + '</t></is></c>';
            }).join("");
            return '<row r="' + number + '">' + cells + '</row>';
        }).join("");
        const filter = sheet.freezeColumns ? '<autoFilter ref="A' + sheet.headingRow + ':' +
            columnName(sheet.widths.length - 1) + sheet.rows.length + '"/>' : "";
        return '<worksheet xmlns="' + sheetNamespace + '">' + frozen + columns +
            '<sheetData>' + rows + '</sheetData>' + filter + '</worksheet>';
    }

    const styles = '<styleSheet xmlns="' + sheetNamespace + '">' +
        '<numFmts count="1"><numFmt numFmtId="164" formatCode="0.0##"/></numFmts>' +
        '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font>' +
        '<font><b/><sz val="11"/><color rgb="FF17345D"/><name val="Calibri"/></font>' +
        '<font><b/><sz val="11"/><color rgb="FF91202A"/><name val="Calibri"/></font></fonts>' +
        '<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>' +
        '<fill><patternFill patternType="solid"><fgColor rgb="FFEAF3FA"/><bgColor indexed="64"/></patternFill></fill>' +
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFE8EA"/><bgColor indexed="64"/></patternFill></fill></fills>' +
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
        '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment wrapText="1"/></xf>' +
        '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' +
        '<xf numFmtId="164" fontId="2" fillId="3" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1"/></cellXfs>' +
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>';

    function create(sheets) {
        const entry = (name, xml) => ({ name, bytes: writer.encode(declaration + xml) });
        const targets = sheets.map((_, index) => 'worksheets/sheet' + (index + 1) + '.xml');
        const book = '<workbook xmlns="' + sheetNamespace + '" xmlns:r="' + documentRelationships + '">' +
            '<bookViews><workbookView/></bookViews><sheets>' + sheets.map((sheet, index) =>
                '<sheet name="' + escapeXml(sheet.name) + '" sheetId="' + (index + 1) + '" r:id="rId' + (index + 1) + '"/>')
                .join("") + '</sheets></workbook>';
        const types = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
            '<Default Extension="xml" ContentType="application/xml"/>' +
            '<Override PartName="/xl/workbook.xml" ContentType="' + mime + '.main+xml"/>' +
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
            targets.map(target => '<Override PartName="/xl/' + target +
                '" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>').join("") +
            '</Types>';
        const files = [
            entry('[Content_Types].xml', types),
            entry('_rels/.rels', relationships([['officeDocument', 'xl/workbook.xml']])),
            entry('xl/workbook.xml', book),
            entry('xl/_rels/workbook.xml.rels', relationships([...targets.map(target => ['worksheet', target]), ['styles', 'styles.xml']])),
            entry('xl/styles.xml', styles),
            ...sheets.map((sheet, index) => entry('xl/' + targets[index], worksheet(sheet)))
        ];
        return window.PortalReportPDF.zip(files, { allowPaths: true }).slice(0, undefined, mime);
    }

    window.PortalGradeWorkbook = Object.freeze({ create });
}());
