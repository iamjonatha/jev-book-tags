"""Build an edited walkthrough from the verified native-dialog captures."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];MEDIA=ROOT/'docs/media';WORK=ROOT/'demo/media-work'
chapters=[('01-intro.png',5,'JEV Book Tags'),('02-settings.png',7,'A clean settings screen'),
          ('09-threshold-before.png',3,'Open Advanced options: empty category cells inherit 85%'),
          ('09-threshold.png',7,'Set Programming to 0.95: category threshold 95%'),
          ('10-single.png',8,'Single book: clickable tag choices'),
          ('03-review.png',10,'32 real evaluations: 31 ready, one to review'),
          ('11-review-detail.png',9,'Review only the uncertain book'),
          ('04-apply.png',8,'Apply 31 ready books; preserve existing tags'),
          ('05-editor.png',7,'Classify from the metadata editor'),
          ('06-results.png',8,'Genuine cached responses; no new API calls'),('07-outro.png',4,'Start with your library')]


def playlist(name,items):
    path=WORK/name
    lines=['ffconcat version 1.0']
    for image,duration,*_ in items:
        lines.extend(["file '"+str(MEDIA/image)+"'",f'duration {duration}'])
    lines.append("file '"+str(MEDIA/items[-1][0])+"'")
    path.write_text('\n'.join(lines)+'\n');return path

source=playlist('video.ffconcat',chapters)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-safe','0','-f','concat','-i',str(source),
                '-vf','scale=1280:720:flags=lanczos,fps=30,format=yuv420p',
                '-c:v','libx264','-preset','medium','-crf','20','-movflags','+faststart',
                '-an',str(MEDIA/'jev-book-tags-demo.mp4')],check=True)
short=[('01-intro.png',3),('09-threshold-before.png',2),('09-threshold.png',3),('10-single.png',4),('03-review.png',5),('11-review-detail.png',4),('04-apply.png',5)]
source=playlist('gif.ffconcat',short)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-safe','0','-f','concat','-i',str(source),
                '-filter_complex','fps=5,scale=1120:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3',
                '-loop','0',str(MEDIA/'jev-book-tags-demo.gif')],check=True)
(MEDIA/'chapters.json').write_text(json.dumps([{'image':i,'duration_seconds':d,'title':t} for i,d,t in chapters],indent=2)+'\n')
print('Built MP4 and GIF. Duration:',sum(x[1] for x in chapters),'seconds; GIF:',sum(x[1] for x in short),'seconds')
