"""Stage a verified integrated backup into a NEW separated data directory only."""
import argparse,json
from pathlib import Path
from .photo_backup import restore

def stage(archive,destination):
    dest=Path(destination)
    if not dest.is_absolute():raise ValueError('새 데이터 폴더는 절대 경로여야 합니다.')
    # restore validates hashes, refuses existing directories, checks DB integrity,
    # rewrites photo roots and invalidates restored sessions before publishing.
    result=restore(archive,dest,True)
    database=dest/'Database';database.mkdir()
    (dest/'warehouse.db').replace(database/'warehouse.db')
    (dest/'Logs').mkdir()
    return {'data_directory':str(dest.resolve()),'database':str(database/'warehouse.db'),
            'automatic_backup':False,'note':'기존 데이터는 변경하지 않았습니다. 백업 경로/자동 백업을 재설정하고 수동으로 연결을 전환하세요.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True);parser.add_argument('--destination',required=True)
    parser.add_argument('--confirm',action='store_true');args=parser.parse_args()
    if not args.confirm:
        from .photo_backup import verify
        report=verify(args.archive);report.pop('manifest',None)
        print(json.dumps({'verified':report,'action':'검증만 수행했습니다. 새 폴더 생성은 --confirm 필요'},ensure_ascii=False));return
    print(json.dumps(stage(args.archive,args.destination),ensure_ascii=False))

if __name__=='__main__':main()
