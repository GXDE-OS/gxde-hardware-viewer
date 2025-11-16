build:
	pylupdate6 gxde-hardware-viewer.py -ts translations/gxde-hardware-viewer_*.ts
	bash translate_generation.sh

install:
	mkdir -pv $(DESTDIR)/usr/share/applications
	mkdir -pv $(DESTDIR)/usr/share/gxde-hardware-viewer/
	mkdir -pv $(DESTDIR)/usr/bin
	cp -rv gxde-hardware-viewer.desktop $(DESTDIR)/usr/share/applications
	cp -rv gxde-hardware-viewer.py $(DESTDIR)/usr/bin/gxde-hardware-viewer
	cp -rv translations $(DESTDIR)/usr/share/gxde-hardware-viewer/