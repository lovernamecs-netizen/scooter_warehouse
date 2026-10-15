// Conservative candidates only; never confirm OCR automatically.
export function validVin(value) { return /^[A-HJ-NPR-Z0-9]{17}$/.test(value) && /[0-9]/.test(value); }
export function vinCandidates(raw, fallback=[]) {
  const labelled = new Set(), other = new Set();
  let found = other;
  function add(value) {
    if (!/^[A-Z0-9]{17}$/.test(value) || !/[0-9]/.test(value)) return;
    const corrected = value.replace(/O|Q/g,'0').replace(/I/g,'1');
    if (validVin(corrected)) found.add(corrected);
  }
  const lines = raw ? String(raw).toUpperCase().split(/[\r\n]+/) : fallback.map(String);
  for (let line of lines) {
    line = line.toUpperCase().trim();
    const label=/^(?:(?:VIN|CHASSIS|FRAME)(?:\s*(?:NO|NUMBER)\.?)?|NO\.?|차대번호)\s*[:：.#-]?\s*/;
    found=label.test(line)?labelled:other;
    line=line.replace(label,'');
    // Full tokens only: never take a 17-character slice of a longer string.
    for (const token of line.match(/[A-Z0-9]+/g)||[]) add(token);
    if (/^[A-Z0-9\s*-]+$/.test(line)) add(line.replace(/[\s*-]/g,''));
  }
  return [...new Set([...labelled,...other])].slice(0,12);
}

// Both S and 5 are retained as possibilities; positions are not model-specific.
export function vinAmbiguities(value) {
  if (!validVin(value)) return [];
  return [...value].flatMap((char,index)=>char==='S'||char==='5' ? [{index,from:char,to:char==='S'?'5':'S'}] : []);
}
export function swapVinCharacter(value,index) {
  const item=vinAmbiguities(value).find(x=>x.index===index);
  return item ? value.slice(0,index)+item.to+value.slice(index+1) : value;
}
