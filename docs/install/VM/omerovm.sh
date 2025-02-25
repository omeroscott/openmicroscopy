#!/bin/bash

export VMNAME=${VMNAME:-"$1"}
export VMNAME=${VMNAME:-"omero-vm"}

export MEMORY=${MEMORY:-"1024"}
export SSH_PF=${SSH_PF:-"2222"}
export OMERO_PORT=${OMERO_PORT:-"4063"}
export OMERO_PF=${OMERO_PF:-"4063"}
export OMEROS_PORT=${OMEROS_PORT:-"4064"}
export OMEROS_PF=${OMEROS_PF:-"4064"}

set -e
set -u
set -x

if test -e $HOME/Library/VirtualBox; then
    export HARDDISKS=${HARDDISKS:-"$HOME/Library/VirtualBox/HardDisks/"}
elif test -e $HOME/.VirtualBox; then
    export HARDDISKS=${HARDDISKS:-"$HOME/.VirtualBox/HardDisks/"}
else
    echo "Cannot find harddisks! Trying setting HARDDISKS"
    exit 3
fi

VBOX="VBoxManage --nologo"

$VBOX list vms | grep "$VMNAME" || {
	VBoxManage clonehd "$HARDDISKS"omero-base-image-debian-6.vdi"" "$HARDDISKS$VMNAME.vdi"
	VBoxManage createvm --name "$VMNAME" --register --ostype "Debian"
	VBoxManage storagectl "$VMNAME" --name "IDE CONTROLLER" --add ide
	VBoxManage storagectl "$VMNAME" --name "SATA CONTROLLER" --add sata
	VBoxManage storageattach "$VMNAME" --storagectl "SATA CONTROLLER" --port 0 --device 0 --type hdd --medium $HARDDISKS$VMNAME.vdi
		
	VBoxManage modifyvm "$VMNAME" --nic1 nat --nictype1 "82540EM"
	
	VBoxManage modifyvm "$VMNAME" --memory $MEMORY --acpi on
	
	VBoxManage setextradata "$VMNAME" "VBoxInternal/Devices/e1000/0/LUN#0/Config/ssh/HostPort" $SSH_PF
	VBoxManage setextradata "$VMNAME" "VBoxInternal/Devices/e1000/0/LUN#0/Config/ssh/GuestPort" 22
	VBoxManage setextradata "$VMNAME" "VBoxInternal/Devices/e1000/0/LUN#0/Config/ssh/Protocol" TCP
	VBoxManage setextradata "$VMNAME" "VBoxInternal/Devices/e1000/0/LUN#0/Config/omeroserver/HostPort" $OMERO_PF
	VBoxManage setextradata "$VMNAME" "VBoxInternal/Devices/e1000/0/LUN#0/Config/omeroserver/GuestPort" $OMERO_PORT
	VBoxManage setextradata "$VMNAME" "VBoxInternal/Devices/e1000/0/LUN#0/Config/omeroservers/Protocol" TCP
	VBoxManage setextradata "$VMNAME" "VBoxInternal/Devices/e1000/0/LUN#0/Config/omeroservers/HostPort" $OMEROS_PF
	VBoxManage setextradata "$VMNAME" "VBoxInternal/Devices/e1000/0/LUN#0/Config/omeroservers/GuestPort" $OMEROS_PORT
	VBoxManage setextradata "$VMNAME" "VBoxInternal/Devices/e1000/0/LUN#0/Config/omeroserver/Protocol" TCP
	
	sleep 5
}

$VBOX list runningvms | grep "$VMNAME" || {
    echo "Starting VM..."
    $VBOX startvm "$VMNAME" --type headless
    echo "Give the VM time to boot..."
    sleep 30
}

echo "Cleaning up any old OMERO.VM keys"
ssh-keygen -R [localhost]:2222 -f ~/.ssh/known_hosts
rm -f omerokey omerokey.pub

echo "Generat a new DSA keypair"
ssh-keygen -t dsa -f omerokey -N ''
cp omerokey ~/.ssh/omerokey
cp omerokey.pub ~/.ssh/omerokey.pub

echo "Enforce correct permissions for key"
chmod 600 ./omerokey
chmod 600 ~/.ssh/omerokey*

SCP="scp -2 -v -o NoHostAuthenticationForLocalhost=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o CheckHostIP=no -o PasswordAuthentication=no -o ChallengeResponseAuthentication=no -o PreferredAuthentications=publickey -i omerokey -P $SSH_PF"
SSH="ssh -2 -v -o StrictHostKeyChecking=no -i omerokey -p $SSH_PF -t"

SCP_K="scp -v -o StrictHostKeyChecking=no -o NoHostAuthenticationForLocalhost=yes -P $SSH_PF"
SSH_K="ssh -v -o StrictHostKeyChecking=no -o NoHostAuthenticationForLocalhost=yes -p $SSH_PF -t"


[ -f omerokey.pub ] && {    
    echo "Copying DSA key to VM"
	expect -c "spawn $SCP_K omerokey.pub omero@localhost:~/; expect \"*?assword:*\"; send \"omero\n\r\"; interact"
	expect -c "spawn $SCP_K setup_keys.sh omero@localhost:~/; expect \"*?assword:*\"; send \"omero\n\r\"; interact"

	echo "Execute the key setup script"
	expect -c "spawn $SSH_K omero@localhost sh /home/omero/setup_keys.sh; expect \"*?assword:*\"; send \"omero\n\r\"; interact"
} || echo "Local DSAAuthentication key was not found. Use: $ ssh-keygen -t dsa"

echo "Copying scripts to VM"
$SCP driver.sh omero@localhost:~/
$SCP setup_userspace.sh omero@localhost:~/
$SCP setup_environment.sh omero@localhost:~/
$SCP setup_omero.sh omero@localhost:~/
$SCP omero-init.d omero@localhost:~/

echo "ssh : exec driver.sh"
$SSH omero@localhost 'sh /home/omero/driver.sh'

sleep 40

echo "ALL DONE!"
echo "Connect to your OMERO VM using either OMERO.insight or another OMERO client or SSH using the connect.sh script"
echo "Your VM has the following IP addresses:"
VBoxManage guestproperty enumerate $VMNAME | grep IP
