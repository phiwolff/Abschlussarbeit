import yaml
import opt
import simulate
import export_svg
from tkinter import filedialog

def load_config():

    with open("config.yaml", 'r') as stream:
        try:
            config = yaml.safe_load(stream)   
            return config
        except yaml.YAMLError as exc:
            print(exc)



if __name__ == "__main__":

    print('Welche json Datei soll geladen werden, um deren Polygone nach Vorzeichen zu optimieren und die Geschwindigkeit an den Wärmeeintrag anzupassen?')
    file_path = filedialog.askopenfilename()
    cfg = load_config()
    optList, minCutting = opt.main(cfg,file_path)  
    if cfg.get('processing_settings')['export_settings']['make_svg_opt'] == True:
        export_svg.main(optList,file_path)

    simulate.main(cfg, optList, minCutting, file_path)
