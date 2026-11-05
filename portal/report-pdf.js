(function () {
    "use strict";
    const base = new URL(".", document.currentScript.src);
    let resources;
    function script(file, ready) {
        if (ready()) return Promise.resolve();
        return new Promise((resolve, reject) => {
            const element = document.createElement("script"); element.src = new URL(file, base).href;
            element.onload = () => ready() ? resolve() : reject(new Error("Recurso PDF incompleto"));
            element.onerror = () => { element.remove(); reject(new Error("No se pudieron cargar los recursos PDF. Recarga y vuelve a descargar el lote.")); };
            document.head.append(element);
        });
    }
    function load() {
        resources ||= Promise.all([script("vendor/jspdf/jspdf.umd.min.js", () => Boolean(window.jspdf?.jsPDF)), script("report-pdf-assets.js", () => Boolean(window.PortalReportPDFAssets))]).catch(error => { resources = undefined; throw error; });
        return resources;
    }
    const months = ["ENERO","FEBRERO","MARZO","ABRIL","MAYO","JUNIO","JULIO","AGOSTO","SEPTIEMBRE","OCTUBRE","NOVIEMBRE","DICIEMBRE"];
    const ordinals = ["","PRIMERO","SEGUNDO","TERCERO","CUARTO","QUINTO","SEXTO","SÉPTIMO","OCTAVO"];
    function courseCode(formation) {
        const semester=formation?.semester,stage=formation?.stage_code;
        if(!Number.isInteger(semester)||semester<1||!['introductorio','filosofia','teologia'].includes(stage))return 'PENDIENTE';
        return (stage==='introductorio'?'CI':Math.ceil(semester/2)+(stage==='filosofia'?'F':'T'))+'-'+semester;
    }
    function period(value) {
        const a=value.starts_on.split("-"),b=value.ends_on.split("-");
        return months[Number(a[1])-1]+(a[0]===b[0]?" A ":" "+a[0]+" A ")+months[Number(b[1])-1]+" "+b[0];
    }
    async function pdf(issue) {
        const d=issue?.snapshot;
        if (!d || d.version!==1 || d.scale!==10 || !Array.isArray(d.rows) || !d.rows.length || d.rows.some(r=>typeof r.name!=="string"||typeof r.score!=="number"||!Number.isFinite(r.score)||r.score<0||r.score>10)) throw new Error("Boleta emitida inválida");
        const average=Math.round(d.rows.reduce((total,r)=>total+Math.round(r.score*10),0)/d.rows.length)/10;
        const printedRows=[...d.rows,{name:'PROMEDIO SEMESTRAL',score:average,summary:true}];
        await load();
        const doc=new window.jspdf.jsPDF({orientation:"portrait",unit:"pt",format:"letter",compress:true,putOnlyUsedFonts:true});
        const assets=window.PortalReportPDFAssets;
        doc.addFileToVFS("LiberationSans.ttf",assets.regular);doc.addFont("LiberationSans.ttf","ReportSans","normal");
        doc.addFileToVFS("LiberationSans-Bold.ttf",assets.bold);doc.addFont("LiberationSans-Bold.ttf","ReportSans","bold");
        doc.setProperties({title:issue.folio,author:"Seminario de Matamoros-Reynosa",subject:"Boleta de calificaciones"});
        doc.setCreationDate(new Date(issue.issued_at));
        if (/^[a-f0-9-]{36}$/i.test(issue.id)) doc.setFileId(issue.id.replaceAll("-",""));
        const split=(text,size,width,bold=false)=>{doc.setFont("ReportSans",bold?"bold":"normal");doc.setFontSize(size);return doc.splitTextToSize(String(text||""),width);};
        const signatureLines=[d.rector_name,d.prefect_name].map(n=>split(n,10,238));
        const signatureHeight=Math.max(...signatureLines.map(a=>a.length))*12+20;
        const footerY=758,signatureY=footerY-34-signatureHeight,limit=signatureY-30;
        function layout(scale) {
            const size=10*scale,padding=4*scale;
            const name=split(d.student.full_name,size,235),number=split(d.student.student_number,size,148);
            const infoY=34+(220-34)*scale,infoHeight=(Math.max(name.length,number.length)+1)*13*scale;
            const tableY=infoY+infoHeight+18*scale;
            const rows=printedRows.map(r=>{const lines=split(r.name,size,352,Boolean(r.summary));return {row:r,lines,height:lines.length*13*scale+padding*2};});
            return {scale,size,padding,name,number,infoY,infoHeight,tableY,rows,bottom:tableY+23*scale+rows.reduce((a,r)=>a+r.height,0)};
        }
        let scale=1,plan=layout(scale);
        for(let i=0;i<30&&plan.bottom>limit;i++){scale*=Math.min(.95,(limit-34)/(plan.bottom-34)*.99);plan=layout(scale);}
        if(plan.bottom>limit)throw new Error("No fue posible ajustar la boleta completa a una hoja");
        const text=(value,x,y,size=10,bold=false,align="left")=>{doc.setFont("ReportSans",bold?"bold":"normal");doc.setFontSize(size);doc.text(value,x,y,{align,lineHeightFactor:1.3});};
        const y=top=>34+(top-34)*scale;
        doc.addImage(assets.crest,"PNG",306-26*scale,34,52*scale,52*scale,undefined,"FAST");
        text(d.institution.name,306,y(110),17*scale,true,"center");
        text([d.formation?.stage_name,d.formation?.ecclesial_name].filter(Boolean).join(" - ").toLocaleUpperCase("es"),306,y(144),10.5*scale,true,"center");
        text("BOLETA DE CALIFICACIONES",306,y(158),10.5*scale,true,"center");
        text("CICLO "+d.cycle,306,y(172),10.5*scale,true,"center");
        text(period(d.period),306,y(188),9*scale,false,"center");
        text("NOMBRE:",42,plan.infoY,plan.size,true);text(plan.name,100,plan.infoY,plan.size);
        const groupY=plan.infoY+Math.max(plan.name.length,1)*13*scale+3*scale;
        text("GRUPO:",42,groupY,plan.size,true);text(courseCode(d.formation),100,groupY,plan.size);
        text("MATRÍCULA:",345,plan.infoY,plan.size,true);text(plan.number,422,plan.infoY,plan.size);
        text("SEMESTRE:",345,plan.infoY+Math.max(1,plan.number.length)*13*scale+3*scale,plan.size,true);text(ordinals[d.formation?.semester]||"",422,plan.infoY+Math.max(1,plan.number.length)*13*scale+3*scale,plan.size);
        const x=64,width=484,divider=432,header=23*scale;
        doc.setDrawColor(0);doc.setLineWidth(.5);doc.rect(x,plan.tableY,width,header);doc.line(divider,plan.tableY,divider,plan.tableY+header);
        text("MATERIAS",(x+divider)/2,plan.tableY+15*scale,plan.size,true,"center");
        text("CALIFICACIÓN",(divider+x+width)/2,plan.tableY+15*scale,plan.size,true,"center");
        let rowY=plan.tableY+header;
        for(const row of plan.rows){
            if(row.row.score<=6.9){doc.setFillColor(255,0,0);doc.rect(divider,rowY,x+width-divider,row.height,'F');}
            doc.rect(x,rowY,width,row.height);doc.line(divider,rowY,divider,rowY+row.height);
            text(row.lines,x+8,rowY+plan.padding+plan.size,plan.size,Boolean(row.row.summary));
            text(row.row.score.toFixed(1),(divider+x+width)/2,rowY+row.height/2+plan.size*.35,plan.size,true,"center");rowY+=row.height;
        }
        for(let i=0;i<2;i++){
            const left=i===0?42:330,center=left+120;doc.line(left,signatureY,left+240,signatureY);
            text(signatureLines[i],center,signatureY+16,10,false,"center");
            text(i===0?"Rector":"Prefecto de Estudios",center,signatureY+16+signatureLines[i].length*12,10,false,"center");
        }
        const date=new Date(issue.issued_at).toLocaleDateString("es-MX",{timeZone:"America/Matamoros"});
        text(issue.folio+" · Emitida "+date+" · Escala 0–10 · Mínima aprobatoria 7.0",306,footerY,8,false,"center");
        if(doc.getNumberOfPages()!==1)throw new Error("La boleta no quedó en una sola hoja");
        return new Uint8Array(doc.output("arraybuffer"));
    }
    // ZIP sin recompresión: los PDF ya llevan sus flujos comprimidos.
    const crcTable=Uint32Array.from({length:256},(_,n)=>{for(let i=0;i<8;i++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
    function crc32(data){let n=0xffffffff;for(const b of data)n=crcTable[(n^b)&255]^(n>>>8);return(n^0xffffffff)>>>0;}
    function zip(files){
        if(!Array.isArray(files)||!files.length||files.length>201)throw new Error("Lote ZIP inválido");
        const encoder=new TextEncoder(),local=[],central=[];let offset=0;const seen=new Set();
        const header=(length)=>{const bytes=new Uint8Array(length);return {bytes,v:new DataView(bytes.buffer)};};
        for(const file of files){
            if(typeof file.name!=="string"||file.name.includes("/")||file.name.includes("\\")||file.name.includes("..")||seen.has(file.name)||!(file.bytes instanceof Uint8Array))throw new Error("Nombre/archivo ZIP inválido");
            seen.add(file.name);const name=encoder.encode(file.name),data=file.bytes,crc=crc32(data);
            const h=header(30);h.v.setUint32(0,0x04034b50,true);h.v.setUint16(4,20,true);h.v.setUint16(6,0x800,true);h.v.setUint16(12,33,true);h.v.setUint32(14,crc,true);h.v.setUint32(18,data.length,true);h.v.setUint32(22,data.length,true);h.v.setUint16(26,name.length,true);
            local.push(h.bytes,name,data);
            const c=header(46);c.v.setUint32(0,0x02014b50,true);c.v.setUint16(4,20,true);c.v.setUint16(6,20,true);c.v.setUint16(8,0x800,true);c.v.setUint16(14,33,true);c.v.setUint32(16,crc,true);c.v.setUint32(20,data.length,true);c.v.setUint32(24,data.length,true);c.v.setUint16(28,name.length,true);c.v.setUint32(42,offset,true);central.push(c.bytes,name);
            offset+=30+name.length+data.length;
            if(offset>64*1024*1024)throw new Error("El ZIP supera 64 MB; divide la descarga en grupos más pequeños");
        }
        const size=central.reduce((n,p)=>n+p.length,0),end=header(22);end.v.setUint32(0,0x06054b50,true);end.v.setUint16(8,files.length,true);end.v.setUint16(10,files.length,true);end.v.setUint32(12,size,true);end.v.setUint32(16,offset,true);
        return new Blob([...local,...central,end.bytes],{type:"application/zip"});
    }
    function filename(issue){const clean=v=>String(v||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-zA-Z0-9_-]+/g,"_").slice(0,80);return clean(issue.snapshot.student.full_name)+"_"+clean(issue.snapshot.student.student_number)+"_"+clean(issue.folio)+"_"+clean(issue.id).slice(0,8)+".pdf";}
    window.PortalReportPDF=Object.freeze({pdf,zip,filename});
})();
